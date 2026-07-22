"""Database models (SQLModel) and the LLM extraction contract."""

from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum

from pydantic import BaseModel, Field as PydField
from sqlmodel import Field, SQLModel, UniqueConstraint


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class Category(str, Enum):
    """The PRIMARY axis: the trading style an item speaks to. Values are human-readable and
    used verbatim by the LLM. (The tech dimension lives on the secondary ``Approach`` axis.)"""

    TECHNICAL_ANALYSIS = "Technical Analysis"
    MACRO_ANALYSIS = "Macro Analysis"
    INTRADAY_TRADING = "Intraday Trading"
    SWING_TRADING = "Swing Trading"
    FUNDAMENTAL_ANALYSIS = "Fundamental Analysis"
    QUANT_FIRMS = "Quant Firms"


class Approach(str, Enum):
    """The SECONDARY axis: which kind of tech an item uses. Rendered as sub-tags under the
    trading-style category (e.g. "Agentic AI · Intraday Trading"). 0-2 apply to most items."""

    AGENTIC_AI = "Agentic AI"
    MACHINE_LEARNING = "Machine Learning"
    AUTOMATION = "Automation"
    SENTIMENT_NEWS = "Sentiment & News"
    INFRA_DATA = "Infrastructure & Data"
    RISK_SIZING = "Risk & Sizing"


class ItemType(str, Enum):
    """What KIND of item this is — the axis that drives the newsletter's launch-focused
    sections (New Launches, Watch List). Human-readable values used verbatim by the LLM."""

    LAUNCH = "launch"            # a shipped product / feature / platform a trader can use now
    FUNDING = "funding"          # a funding round or acquisition of a trading-relevant company
    EARLY_STAGE = "early_stage"  # announced / beta / waitlist — not generally usable yet
    HIRING = "hiring"            # a job posting / open role at a trading, quant, or HFT firm
    RESEARCH = "research"        # papers, methods, backtests, model write-ups
    DISCUSSION = "discussion"    # community threads, experience reports
    TOOLING = "tooling"          # updates to existing OSS / infra / tools (the default bucket)


class Region(str, Enum):
    """Geographic focus of an item. Drives the India tab + newsletter India section."""

    INDIA = "India"
    GLOBAL = "Global"


class WorkflowStage(str, Enum):
    """Which part of the trading workflow a launch touches. Only set for launch/funding/
    early_stage items; None otherwise. Display-only (not a filter in v1)."""

    RESEARCH = "Research"
    SIGNAL = "Signal Generation"
    EXECUTION = "Execution"
    RISK = "Risk"
    MONITORING = "Monitoring"


class RawItem(SQLModel, table=True):
    """A single ingested item from any source, before AI filtering.

    Dedup is enforced by the unique (source, external_id) pair — re-ingesting the same
    item is a no-op.
    """

    __table_args__ = (UniqueConstraint("source", "external_id", name="uq_source_external"),)

    id: int | None = Field(default=None, primary_key=True)
    source: str = Field(index=True)          # github | reddit | rss | forum | mcp | twitter | bluesky | numerai | stocktwits | careers
    source_key: str = Field(default="", index=True)  # stable per-resource provenance, e.g. github:owner/repo
    external_id: str
    url: str
    title: str
    body: str = ""
    author: str | None = None
    created_at: datetime | None = None       # timestamp from the source, when available
    fetched_at: datetime = Field(default_factory=_utcnow)
    content_hash: str = ""
    raw_json: str | None = None
    processed: bool = Field(default=False, index=True)


class SourceRegistry(SQLModel, table=True):
    """A discovered resource and its measured editorial quality."""

    __table_args__ = (UniqueConstraint("source_key", name="uq_source_registry_key"),)

    id: int | None = Field(default=None, primary_key=True)
    source_key: str = Field(index=True)
    adapter: str = Field(index=True)
    name: str
    url: str = ""
    target: str | None = None
    status: str = Field(default="active", index=True)  # candidate | active | suspended
    first_seen_at: datetime = Field(default_factory=_utcnow)
    last_seen_at: datetime = Field(default_factory=_utcnow, index=True)
    last_fetched_at: datetime | None = Field(default=None, index=True)
    failure_count: int = Field(default=0)


class Insight(SQLModel, table=True):
    """A synthesized, high-value insight distilled from a RawItem by the LLM."""

    id: int | None = Field(default=None, primary_key=True)
    raw_item_id: int = Field(foreign_key="rawitem.id", index=True)
    relevance_score: int = Field(index=True)
    category: str = Field(index=True)        # stores Category.value (trading style)
    approaches: str = "[]"                    # JSON array of Approach.value, e.g. ["Agentic AI"]
    item_type: str = Field(default="tooling", index=True)  # stores ItemType.value
    region: str = Field(default="Global", index=True)      # stores Region.value
    workflow_stage: str | None = None         # stores WorkflowStage.value; only for launch-ish items
    technical_summary: str
    trader_impact: str
    model_used: str = ""
    created_at: datetime = Field(default_factory=_utcnow, index=True)


class DailyBrief(SQLModel, table=True):
    """The editorial layer for a given day's brief, stored as a JSON payload.

    Generated by the LLM at newsletter-write time and persisted so the live API can render
    the brief (which happens per request) without ever calling the LLM. One row per date.
    ``payload_json`` holds ``{theme, editor_note, picks: {insight_id: {summary}}}``.
    """

    id: int | None = Field(default=None, primary_key=True)
    brief_date: str = Field(index=True, unique=True)   # ISO date, e.g. "2026-07-17"
    payload_json: str
    model_used: str = ""
    generated_at: datetime = Field(default_factory=_utcnow)


class InsightExtraction(BaseModel):
    """Structured output contract every LLM provider must return for a raw item.

    Kept free of numeric/length JSON-schema constraints so it works with Claude's
    structured-output mode; the score range is validated in application code.
    """

    relevance_score: int = PydField(
        description="How useful this is to a self-directed retail/algo trader, 1 (noise) to 10 "
        "(genuinely actionable). Reward things a trader could actually try or use."
    )
    category: Category = PydField(
        description="The single trading style this best speaks to (Technical Analysis, Macro "
        "Analysis, Intraday Trading, Swing Trading, Fundamental Analysis, or Quant Firms)."
    )
    approaches: list[Approach] = PydField(
        default_factory=list,
        description="The 0-2 kinds of tech this item uses (Agentic AI, Machine Learning, "
        "Automation, Sentiment & News, Infrastructure & Data, Risk & Sizing). Empty if none fit.",
    )
    item_type: ItemType = PydField(
        default=ItemType.TOOLING,
        description="What kind of item this is: launch (a product/feature a trader can use now), "
        "funding (a raise/acquisition), early_stage (announced/beta/waitlist), research, "
        "discussion, or tooling (default). Use launch/funding/early_stage only for genuine news.",
    )
    region: Region = PydField(
        default=Region.GLOBAL,
        description="India if the item is about Indian markets (NSE/BSE, Nifty/Bank Nifty, "
        "Zerodha/Upstox/Dhan, SEBI, Indian fintechs) or by/for Indian traders; otherwise Global.",
    )
    workflow_stage: WorkflowStage | None = PydField(
        default=None,
        description="Only for launch/funding/early_stage items: which part of the trading workflow "
        "it touches — Research, Signal Generation, Execution, Risk, or Monitoring. Null otherwise.",
    )
    technical_summary: str = PydField(
        description="2-3 plain-English sentences a self-directed trader would understand: what it "
        "is and what it actually does. No academic jargon, no marketing fluff, no PhD math."
    )
    trader_impact: str = PydField(
        description="How a retail/independent trader could actually use this to trade better or "
        "make money — the concrete edge, tool, or workflow it unlocks."
    )
