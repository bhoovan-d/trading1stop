"""Twitter / X ingestion — STUBBED.

The official X API is paid and gated, so this adapter ships disabled. It implements the
Source interface and short-circuits unless BOTH ``TWITTER_ENABLED=true`` and a bearer token
are present. When you obtain credentials, implement ``_fetch_enabled`` against the X API v2
``/2/tweets/search/recent`` (or user-timeline) endpoints — the surrounding pipeline needs no
changes.
"""

from __future__ import annotations

from collections.abc import Iterable

from loguru import logger

from ..config import Settings, TwitterSources
from .base import RawItemDraft, Source


class TwitterSource(Source):
    source = "twitter"

    def __init__(self, settings: Settings, sources: TwitterSources):
        self.settings = settings
        self.cfg = sources

    def fetch(self) -> Iterable[RawItemDraft]:
        enabled = self.settings.twitter_enabled and self.cfg.enabled
        if not enabled:
            logger.info("[twitter] disabled — skipping (set TWITTER_ENABLED=true to enable).")
            return []
        if not self.settings.twitter_bearer_token:
            logger.warning("[twitter] enabled but TWITTER_BEARER_TOKEN missing — skipping.")
            return []
        return self._fetch_enabled()

    def _fetch_enabled(self) -> Iterable[RawItemDraft]:
        # Implement against the X API v2 here when credentials are available.
        # Example shape (left unimplemented on purpose):
        #   for handle in self.cfg.handles:
        #       tweets = x_api.recent_search(f"from:{handle}", bearer=...)
        #       for t in tweets:
        #           yield RawItemDraft(source="twitter", external_id=f"tweet:{t.id}", ...)
        logger.warning("[twitter] adapter is a stub — no X API implementation wired yet.")
        return []
