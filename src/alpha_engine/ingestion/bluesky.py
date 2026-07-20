"""Credential-free Bluesky keyword search ingestion."""

from __future__ import annotations

from collections.abc import Iterable
from datetime import datetime

import httpx
from dateutil.parser import isoparse
from loguru import logger

from ..config import BlueskySources, Settings
from .base import RawItemDraft, Source, truncate

# ``api.bsky.app`` currently serves public search while the ``public`` host rejects
# searchPosts with 403 (other unauthenticated read endpoints work on both hosts).
_SEARCH_URL = "https://api.bsky.app/xrpc/app.bsky.feed.searchPosts"


def _post_url(uri: str, handle: str) -> str:
    """Convert an AT URI to the canonical public Bluesky post URL."""
    rkey = uri.rsplit("/", 1)[-1]
    return f"https://bsky.app/profile/{handle}/post/{rkey}"


def _parse_time(value: str | None) -> datetime | None:
    try:
        return isoparse(value) if value else None
    except (TypeError, ValueError):
        return None


class BlueskySource(Source):
    source = "bluesky"

    def __init__(self, settings: Settings, sources: BlueskySources):
        self.settings = settings
        self.cfg = sources

    def fetch(self) -> Iterable[RawItemDraft]:
        seen: set[str] = set()
        emitted = 0
        for query in self.cfg.queries:
            if emitted >= self.settings.max_items_per_source:
                break
            try:
                response = httpx.get(
                    _SEARCH_URL,
                    params={"q": query, "limit": min(25, self.settings.max_items_per_source)},
                    timeout=20.0,
                )
                response.raise_for_status()
                posts = response.json().get("posts", [])
            except Exception as exc:  # noqa: BLE001 - one query must not sink the source
                logger.warning(f"[bluesky] query {query!r} failed: {exc}")
                continue

            for post_view in posts:
                post = post_view.get("record") or {}
                author = post_view.get("author") or {}
                uri = post_view.get("uri") or ""
                handle = author.get("handle") or author.get("did") or "unknown"
                text = (post.get("text") or "").strip()
                if not uri or not text or uri in seen:
                    continue
                seen.add(uri)
                yield RawItemDraft(
                    source=self.source,
                    external_id=f"bluesky:{uri}",
                    url=_post_url(uri, handle),
                    title=f"[@{handle}] {text[:200]}",
                    body=truncate(text),
                    author=handle,
                    created_at=_parse_time(post.get("createdAt") or post_view.get("indexedAt")),
                    raw={
                        "query": query,
                        "uri": uri,
                        "cid": post_view.get("cid"),
                        "reply_count": post_view.get("replyCount", 0),
                        "repost_count": post_view.get("repostCount", 0),
                        "like_count": post_view.get("likeCount", 0),
                        "quote_count": post_view.get("quoteCount", 0),
                    },
                )
                emitted += 1
                if emitted >= self.settings.max_items_per_source:
                    break
