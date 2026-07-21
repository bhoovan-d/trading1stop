"""Base types for ingestion source adapters."""

from __future__ import annotations

import hashlib
import re
from abc import ABC, abstractmethod
from collections.abc import Iterable
from datetime import datetime
from functools import lru_cache
from typing import Any

from pydantic import BaseModel, Field


class RawItemDraft(BaseModel):
    """A source-produced item before it is persisted / deduped."""

    source: str
    source_key: str = ""  # stable resource-level identifier; defaults to the adapter name
    external_id: str          # stable per-source id -> drives dedup
    url: str
    title: str
    body: str = ""
    author: str | None = None
    created_at: datetime | None = None
    raw: dict[str, Any] = Field(default_factory=dict)

    def content_hash(self) -> str:
        digest = hashlib.sha256()
        digest.update(self.title.encode("utf-8", "ignore"))
        digest.update(b"\x00")
        digest.update(self.body.encode("utf-8", "ignore"))
        return digest.hexdigest()


class Source(ABC):
    """A pluggable ingestion source. Adapters implement :meth:`fetch`."""

    #: short identifier stored on RawItem.source (github, reddit, rss, forum, mcp, twitter, bluesky, numerai, stocktwits)
    source: str = "base"

    @abstractmethod
    def fetch(self) -> Iterable[RawItemDraft]:
        """Yield freshly discovered items. Dedup happens downstream in the repository."""
        raise NotImplementedError


def truncate(text: str, limit: int = 8000) -> str:
    """Keep item bodies bounded so LLM calls stay cheap and within limits."""
    text = text or ""
    return text if len(text) <= limit else text[:limit] + "\n…[truncated]"


@lru_cache(maxsize=512)
def _keyword_pattern(keywords: tuple[str, ...]) -> re.Pattern[str]:
    """A single case-insensitive, word-boundary alternation for the keyword set.

    Word boundaries are essential: a naive substring test makes short tokens like "ai", "ml",
    or "nse" match inside ordinary words ("retail", "html", "sense"), which would pass almost
    everything. ``\\b`` makes each keyword match only as a whole word/phrase.
    """
    parts = [re.escape(k.strip()) for k in keywords if k and k.strip()]
    return re.compile(r"\b(?:" + "|".join(parts) + r")\b", re.IGNORECASE)


def matches_keywords(text: str, keywords: list[str]) -> bool:
    """True if ``text`` contains any keyword as a whole word/phrase. Empty list -> True.

    Used as a cheap ingest-time topic screen so off-topic items never reach the LLM.
    """
    if not keywords:
        return True
    pattern = _keyword_pattern(tuple(keywords))
    return pattern.search(text or "") is not None
