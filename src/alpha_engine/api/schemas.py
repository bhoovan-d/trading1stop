"""API response DTOs."""

from __future__ import annotations

import json
from datetime import datetime

from pydantic import BaseModel

from ..config import stream_for
from ..models import Insight, RawItem


def _parse_approaches(value: str | None) -> list[str]:
    """Decode the stored JSON approaches array, tolerating legacy/empty values."""
    if not value:
        return []
    try:
        parsed = json.loads(value)
    except (json.JSONDecodeError, TypeError):
        return []
    return [str(a) for a in parsed] if isinstance(parsed, list) else []


class InsightOut(BaseModel):
    id: int
    relevance_score: int
    category: str
    approaches: list[str] = []
    item_type: str = "tooling"
    region: str = "Global"
    workflow_stage: str | None = None
    technical_summary: str
    trader_impact: str
    model_used: str
    created_at: datetime
    # joined from RawItem
    source: str
    stream: str  # "alpha" | "community"
    title: str
    url: str
    author: str | None = None
    item_created_at: datetime | None = None

    @classmethod
    def from_row(cls, insight: Insight, raw: RawItem) -> "InsightOut":
        return cls(
            id=insight.id,  # type: ignore[arg-type]
            relevance_score=insight.relevance_score,
            category=insight.category,
            approaches=_parse_approaches(getattr(insight, "approaches", None)),
            item_type=getattr(insight, "item_type", None) or "tooling",
            region=getattr(insight, "region", None) or "Global",
            workflow_stage=getattr(insight, "workflow_stage", None),
            technical_summary=insight.technical_summary,
            trader_impact=insight.trader_impact,
            model_used=insight.model_used,
            created_at=insight.created_at,
            source=raw.source,
            stream=stream_for(raw.source),
            title=raw.title,
            url=raw.url,
            author=raw.author,
            item_created_at=raw.created_at,
        )


class InsightPage(BaseModel):
    items: list[InsightOut]
    total: int
    page: int
    page_size: int


class MetaOut(BaseModel):
    categories: list[str]
    approaches: list[str]
    item_types: list[str]
    regions: list[str]
    sources: list[str]
    score_min: int
    score_max: int
    date_min: str | None
    date_max: str | None
    total_insights: int
    alpha_count: int
    community_count: int


class SourceHealthOut(BaseModel):
    source_key: str
    name: str
    adapter: str
    status: str
    url: str
    qualifying_insights_30d: int
    failure_count: int
    last_seen_at: datetime


class NewsletterList(BaseModel):
    dates: list[str]


class NewsletterOut(BaseModel):
    date: str
    markdown: str
