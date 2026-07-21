"""RSS / Atom ingestion for domain-builder blogs, research feeds, and release streams."""

from __future__ import annotations

import time
from collections.abc import Iterable
from datetime import datetime, timezone
from itertools import islice
from time import struct_time

import feedparser
from loguru import logger

from ..config import RssSources, Settings
from .base import RawItemDraft, Source, matches_keywords, truncate

# Some hosts (notably Reddit) rate-limit anonymous/generic-agent requests aggressively.
# A descriptive User-Agent plus a small pause between feed fetches keeps every run polite.
feedparser.USER_AGENT = "trading-alpha-engine/0.1 (+https://github.com/) feedparser"
_FETCH_DELAY_SECONDS = 1.5


def _to_dt(parsed: struct_time | None) -> datetime | None:
    if not parsed:
        return None
    try:
        return datetime(*parsed[:6], tzinfo=timezone.utc)
    except (ValueError, TypeError):
        return None


def _entry_body(entry) -> str:
    if getattr(entry, "content", None):
        return entry.content[0].get("value", "")
    return getattr(entry, "summary", "") or getattr(entry, "description", "")


class RssSource(Source):
    source = "rss"

    def __init__(self, settings: Settings, sources: RssSources):
        self.settings = settings
        self.cfg = sources

    def _screen_keywords(self, feed) -> list[str] | None:
        """The keyword group a feed's ``screen`` mode selects, or None for no screen."""
        if feed.screen == "ai":
            return self.cfg.screen_keywords_ai
        if feed.screen == "markets":
            return self.cfg.screen_keywords_markets
        return None

    def fetch(self) -> Iterable[RawItemDraft]:
        limit = self.settings.max_items_per_source
        for i, feed in enumerate(self.cfg.feeds):
            if i > 0:
                time.sleep(_FETCH_DELAY_SECONDS)
            try:
                parsed = feedparser.parse(feed.url)
            except Exception as exc:  # noqa: BLE001
                logger.error(f"[rss] {feed.name} parse error: {exc}")
                continue
            if parsed.bozo and not parsed.entries:
                logger.warning(f"[rss] {feed.name} returned no entries ({feed.url}).")
                continue

            screen = self._screen_keywords(feed)
            kept = 0
            for entry in islice(parsed.entries, limit):
                link = getattr(entry, "link", "") or ""
                ext_id = getattr(entry, "id", "") or link
                if not ext_id:
                    continue
                body = truncate(_entry_body(entry))
                # Topic screen: drop off-topic items before they ever reach the LLM.
                if screen is not None and not matches_keywords(
                    f"{getattr(entry, 'title', '')} {body}", screen
                ):
                    continue
                kept += 1
                yield RawItemDraft(
                    source=self.source,
                    source_key=f"rss:{feed.url}",
                    external_id=f"rss:{ext_id}",
                    url=link,
                    title=f"[{feed.name}] {getattr(entry, 'title', 'untitled')}",
                    body=body,
                    author=getattr(entry, "author", None),
                    created_at=_to_dt(
                        getattr(entry, "published_parsed", None)
                        or getattr(entry, "updated_parsed", None)
                    ),
                    raw={"feed": feed.name},
                )
            if screen is not None:
                logger.info(f"[rss] {feed.name} screen='{feed.screen}' kept {kept} item(s).")
