"""Reddit ingestion via public subreddit RSS feeds — no OAuth/credentials required.

Reddit exposes an RSS feed for every subreddit listing (e.g.
``https://www.reddit.com/r/algotrading/top/.rss?t=week``), so we can pull community
threads without a registered app. This is a *community-stream* source: its content is
discussion rather than shipped engineering, and it's held to a lower relevance bar.

Reddit rate-limits anonymous requests per-IP fairly aggressively, so each feed fetch retries
on HTTP 429 with backoff (honoring ``Retry-After``), and there's a polite gap between feeds.
"""

from __future__ import annotations

import re
import time
from collections.abc import Iterable
from datetime import datetime, timezone
from itertools import islice
from time import struct_time

import feedparser
import httpx
from loguru import logger

from ..config import RedditSources, Settings
from .base import RawItemDraft, Source, truncate

# A real browser UA is far less likely to be throttled than a generic bot string.
_UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36"
_FETCH_DELAY_SECONDS = 4.0
_MAX_RETRIES = 3
_BACKOFF_CAP_SECONDS = 30.0
# Reddit "fullname" (t3_<base36>) — the stable per-post id, extracted so dedup survives
# feedparser returning entry.id in different formats across fetches.
_FULLNAME_RE = re.compile(r"t3_[a-z0-9]+", re.IGNORECASE)


def _stable_id(entry, link: str) -> str | None:
    for candidate in (getattr(entry, "id", "") or "", link):
        m = _FULLNAME_RE.search(candidate)
        if m:
            return m.group(0).lower()
    return (getattr(entry, "id", "") or link) or None


def _to_dt(parsed: struct_time | None) -> datetime | None:
    if not parsed:
        return None
    try:
        return datetime(*parsed[:6], tzinfo=timezone.utc)
    except (ValueError, TypeError):
        return None


def _fetch_feed(url: str, label: str):
    """GET an RSS URL, retrying on 429 with backoff. Returns a parsed feed or None."""
    for attempt in range(1, _MAX_RETRIES + 1):
        try:
            resp = httpx.get(url, headers={"User-Agent": _UA}, timeout=20.0, follow_redirects=True)
        except Exception as exc:  # noqa: BLE001
            logger.error(f"[reddit] {label} request error: {exc}")
            return None
        if resp.status_code == 429:
            if attempt == _MAX_RETRIES:
                logger.warning(f"[reddit] {label} rate-limited (429) after {attempt} tries — retry next run.")
                return None
            retry_after = resp.headers.get("retry-after")
            wait = min(float(retry_after), _BACKOFF_CAP_SECONDS) if (retry_after or "").isdigit() else min(
                _BACKOFF_CAP_SECONDS, 5.0 * attempt
            )
            logger.info(f"[reddit] {label} 429 — backing off {wait:.0f}s (try {attempt}/{_MAX_RETRIES}).")
            time.sleep(wait)
            continue
        return feedparser.parse(resp.content)
    return None


class RedditSource(Source):
    source = "reddit"

    def __init__(self, settings: Settings, sources: RedditSources):
        self.settings = settings
        self.cfg = sources

    def _feed_url(self, sub: str) -> str:
        listing = self.cfg.listing
        if listing in ("hot", "new"):
            return f"https://www.reddit.com/r/{sub}/{listing}/.rss"
        return f"https://www.reddit.com/r/{sub}/top/.rss?t={self.cfg.time_filter}"

    def fetch(self) -> Iterable[RawItemDraft]:
        limit = self.settings.max_items_per_source
        for i, sub in enumerate(self.cfg.subreddits):
            if i > 0:
                time.sleep(_FETCH_DELAY_SECONDS)
            parsed = _fetch_feed(self._feed_url(sub), f"r/{sub}")
            if parsed is None:
                continue
            if not parsed.entries:
                logger.warning(f"[reddit] r/{sub} returned no entries.")
                continue

            for entry in islice(parsed.entries, limit):
                link = getattr(entry, "link", "") or ""
                ext_id = _stable_id(entry, link)
                if not ext_id:
                    continue
                if getattr(entry, "content", None):
                    body = entry.content[0].get("value", "")
                else:
                    body = getattr(entry, "summary", "")
                yield RawItemDraft(
                    source=self.source,
                    external_id=f"reddit:{ext_id}",
                    url=link,
                    title=f"[r/{sub}] {getattr(entry, 'title', 'untitled')}",
                    body=truncate(body),
                    author=getattr(entry, "author", None),
                    created_at=_to_dt(
                        getattr(entry, "published_parsed", None)
                        or getattr(entry, "updated_parsed", None)
                    ),
                    raw={"subreddit": sub},
                )
