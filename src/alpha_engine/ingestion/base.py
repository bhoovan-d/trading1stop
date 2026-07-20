"""Base types for ingestion source adapters."""

from __future__ import annotations

import hashlib
from abc import ABC, abstractmethod
from collections.abc import Iterable
from datetime import datetime
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
