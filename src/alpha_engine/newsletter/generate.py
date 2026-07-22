"""Render the daily newsletter — a curated, tiered brief — from stored insights."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime, timezone
from pathlib import Path

from loguru import logger
from sqlmodel import Session, select

from ..config import COMMUNITY_SOURCES, get_settings
from ..db import init_db, session_scope
from ..models import Insight, RawItem
from ..storage import repository

# NOTE: the LLM layer (intelligence.provider, .editorial) is imported lazily inside
# write_newsletter() only — it runs at generation time, not render time. Keeping it out of module
# scope lets the read-only API (which imports markdown_for_date) stay free of openai/anthropic/etc.,
# so the Vercel serverless function stays slim.

# Per-section caps. Everything beyond these is intentionally left out of the newsletter — it still
# lives in the browsable feed. The brief now leads with product news, then strategy, then picks.
WATCH_LIST_COUNT = 3      # early-stage (beta / waitlist / just-announced), flagged not vetted
LAUNCH_COUNT = 4          # shipped launches + funding
HIRING_COUNT = 3          # job postings at quant / HFT firms (India + global)
INDIA_COUNT = 3           # India-focused items (incl. the community carve-out below)
PER_BUCKET_COUNT = 2      # items per strategy bucket (Technical / Macro / Sentiment / Fundamental)
QUANT_FIRMS_COUNT = 2     # "From the Quant Firms" sub-block
WORTH_TRYING_COUNT = 3    # picks worth actually testing (chosen from already-selected items)

# The alpha bar (config.relevance_threshold default 7). The India section admits COMMUNITY items
# only when they clear THIS higher bar — a deliberate exception to the community exclusion below,
# because "how India trades with AI" is mostly community content but must stay curated.
_INDIA_COMMUNITY_MIN = 7

# Strategy buckets for "By Strategy Type". The Sentiment bucket is driven by the approach tag
# (approach wins over category); Quant Firms fold into their own sub-block (bucket None).
_BUCKET_BY_CATEGORY = {
    "Technical Analysis": "Technical",
    "Intraday Trading": "Technical",
    "Swing Trading": "Technical",
    "Macro Analysis": "Macro",
    "Fundamental Analysis": "Fundamental",
}
_BUCKET_ORDER = ["Technical", "Macro", "Sentiment", "Fundamental"]
_LAUNCH_TYPES = {"launch", "funding"}

Row = tuple[Insight, RawItem]


@dataclass
class Sections:
    """The day's picks split into the newsletter's sections. Each Row appears in exactly one
    *primary* section (launches/watch/india/strategy); worth_trying references already-picked
    ids, and what_changed spans every selected item."""

    launches: list[Row] = field(default_factory=list)
    watch_list: list[Row] = field(default_factory=list)
    hiring: list[Row] = field(default_factory=list)
    india: list[Row] = field(default_factory=list)
    strategy: dict[str, list[Row]] = field(default_factory=dict)  # bucket -> rows
    quant_firms: list[Row] = field(default_factory=list)
    worth_trying: list[Row] = field(default_factory=list)

    def selected(self) -> list[Row]:
        """Every row that appears in a primary section, de-duplicated, order preserved."""
        seen: set[int] = set()
        out: list[Row] = []
        buckets = [r for rows in self.strategy.values() for r in rows]
        for row in [*self.launches, *self.watch_list, *self.hiring, *self.india, *buckets, *self.quant_firms]:
            if id(row) not in seen:
                seen.add(id(row))
                out.append(row)
        return out

    def is_empty(self) -> bool:
        return not self.selected()


def strategy_bucket(insight: Insight) -> str | None:
    """Map an insight to a strategy bucket. The Sentiment & News approach tag wins over category;
    Quant Firms return None (rendered in their own sub-block)."""
    if '"Sentiment & News"' in (insight.approaches or ""):
        return "Sentiment"
    return _BUCKET_BY_CATEGORY.get(insight.category)


def _as_date(dt: datetime | None) -> date | None:
    if dt is None:
        return None
    if dt.tzinfo is not None:
        dt = dt.astimezone(timezone.utc)
    return dt.date()


def _rows(session: Session) -> list[Row]:
    # The published brief is the high-signal ALPHA stream only; community discussion
    # (reddit/forums) is browse-only in the UI and deliberately excluded here — with ONE
    # exception: India-region community items that clear the higher alpha bar are admitted so
    # the India section can cover "how India trades with AI" (mostly community) while staying
    # curated. See _INDIA_COMMUNITY_MIN.
    from sqlalchemy import and_, or_

    stmt = (
        select(Insight, RawItem)
        .join(RawItem, Insight.raw_item_id == RawItem.id)
        .where(
            or_(
                RawItem.source.not_in(COMMUNITY_SOURCES),
                and_(Insight.region == "India", Insight.relevance_score >= _INDIA_COMMUNITY_MIN),
            )
        )
        .order_by(Insight.relevance_score.desc(), Insight.created_at.desc())
    )
    return list(session.exec(stmt).all())


def _rows_for_date(session: Session, day: date) -> list[Row]:
    return [(i, r) for i, r in _rows(session) if _as_date(i.created_at) == day]


def available_dates(session: Session) -> list[str]:
    dates = {_as_date(i.created_at) for i in session.exec(select(Insight)).all()}
    return sorted((d.isoformat() for d in dates if d is not None), reverse=True)


def _item_type(insight: Insight) -> str:
    return getattr(insight, "item_type", "tooling") or "tooling"


def _region(insight: Insight) -> str:
    return getattr(insight, "region", "Global") or "Global"


def _select(rows: list[Row]) -> Sections:
    """Assign the day's rows to the newsletter's sections.

    ``rows`` arrive sorted by relevance_score desc. Each row lands in exactly one primary
    section, claimed in priority order so India content is concentrated in its own section and
    product news leads the rest:
      India (region=India) → Watch List (early_stage) → New Launches (launch/funding) →
      By Strategy Type (bucketed) + Quant Firms sub-block.
    Worth Trying is a *fallback* set drawn from already-selected items (the editorial LLM may
    override it). What Changed for Traders spans every selected item and is built at render time.
    """
    sec = Sections()
    used: set[int] = set()

    def take(pred, cap: int) -> list[Row]:
        out: list[Row] = []
        for row in rows:
            if id(row) in used or len(out) >= cap:
                continue
            if pred(row):
                used.add(id(row))
                out.append(row)
        return out

    sec.india = take(lambda r: _region(r[0]) == "India", INDIA_COUNT)
    sec.watch_list = take(lambda r: _item_type(r[0]) == "early_stage", WATCH_LIST_COUNT)
    sec.launches = take(lambda r: _item_type(r[0]) in _LAUNCH_TYPES, LAUNCH_COUNT)
    # Claim job postings before strategy bucketing so they land in "Now Hiring", not the
    # "From the Quant Firms" sub-block (which then holds only firm blog/press).
    sec.hiring = take(lambda r: _item_type(r[0]) == "hiring", HIRING_COUNT)

    # By Strategy Type — bucket the remainder; Quant Firms get their own sub-block.
    for row in rows:
        if id(row) in used:
            continue
        if row[0].category == "Quant Firms" and strategy_bucket(row[0]) is None:
            if len(sec.quant_firms) < QUANT_FIRMS_COUNT:
                used.add(id(row))
                sec.quant_firms.append(row)
            continue
        bucket = strategy_bucket(row[0])
        if bucket is None:
            continue  # no strategy home and not a quant-firm item — left to the browsable feed
        rows_in = sec.strategy.setdefault(bucket, [])
        if len(rows_in) < PER_BUCKET_COUNT:
            used.add(id(row))
            rows_in.append(row)

    # Worth Trying fallback: highest-scored already-selected launches/tooling worth testing.
    selected = sec.selected()
    sec.worth_trying = [
        r for r in selected if _item_type(r[0]) in {"launch", "tooling"}
    ][:WORTH_TRYING_COUNT]
    if not sec.worth_trying:
        sec.worth_trying = selected[:WORTH_TRYING_COUNT]
    return sec


def _truncate_sentence(text: str, max_chars: int = 140) -> str:
    """First sentence of ``text``, hard-capped at ``max_chars`` with an ellipsis."""
    t = " ".join((text or "").split())
    dot = t.find(". ")
    if dot != -1:
        t = t[: dot + 1]
    if len(t) > max_chars:
        t = t[:max_chars].rsplit(" ", 1)[0].rstrip(" ,;:") + "…"
    return t


def _safe_title(raw: RawItem) -> str:
    # Titles already carry a [source] prefix; swap brackets to parens so the markdown link
    # text doesn't nest brackets and break link parsing in the frontend renderer.
    return raw.title.replace("[", "(").replace("]", ")")


def _source_footer(raw: RawItem) -> str:
    return f"<sub>Source: `{raw.source}` · {raw.url}</sub>"


def _copy_for(picks: dict, insight: Insight) -> str | None:
    """The editorial summary for an insight, or None to fall back to its technical field."""
    entry = picks.get(str(insight.id))
    if isinstance(entry, dict):
        summary = entry.get("summary")
        if isinstance(summary, str) and summary.strip():
            return summary.strip()
    return None


_STATUS_LABEL = {"launch": "shipped", "funding": "funded", "early_stage": "early access"}


def _launch_block(insight: Insight, raw: RawItem, copy: str | None) -> list[str]:
    """A rich New-Launches entry: heading, what-it-is prose, and a workflow/status line."""
    header = f"### {insight.relevance_score}/10 · [{_safe_title(raw)}]({raw.url})"
    body = copy or insight.technical_summary.strip()
    meta_bits: list[str] = []
    stage = getattr(insight, "workflow_stage", None)
    if stage:
        meta_bits.append(f"**Touches:** {stage}")
    status = _STATUS_LABEL.get(_item_type(insight))
    if status:
        meta_bits.append(f"**Status:** {status}")
    lines = [header, "", body, ""]
    if meta_bits:
        lines += [" · ".join(meta_bits), ""]
    lines += [_source_footer(raw), ""]
    return lines


def _compact_line(insight: Insight, raw: RawItem, label: str, clause: str) -> str:
    """One renderer-safe line: score · label · [title](url) — clause. No link nested in bold,
    never both starts-and-ends with '*' (which the frontend renderer treats as italic)."""
    return f"**{insight.relevance_score}/10** · {label} · [{_safe_title(raw)}]({raw.url}) — {clause}"


def _job_location(raw: RawItem) -> str:
    """Pull the Location out of a careers item's body header (see careers._compose_body)."""
    head = (raw.body or "").split("\n\n", 1)[0]
    for part in head.split(" · "):
        if part.lower().startswith("location:"):
            return part.split(":", 1)[1].strip()
    return ""


def _render(day: date, rows: list[Row], brief: dict | None = None) -> str:
    title = f"# Trading Alpha Brief — {day.isoformat()}"
    if not rows:
        return f"{title}\n\n_No qualifying insights for this date._\n"

    sec = _select(rows)
    if sec.is_empty():
        return f"{title}\n\n_No qualifying insights for this date._\n"

    brief = brief or {}
    picks = brief.get("picks", {}) if isinstance(brief.get("picks"), dict) else {}
    worth_meta = brief.get("worth_trying", {}) if isinstance(brief.get("worth_trying"), dict) else {}

    intro = brief.get("theme") or (
        f"Today's launches, tools, and India signals for active traders — {len(sec.selected())} picks."
    )
    lines = [title, "", f"*{intro}*", ""]

    editor_note = brief.get("editor_note")
    if isinstance(editor_note, str) and editor_note.strip():
        lines += [editor_note.strip(), ""]

    # ── New Launches ────────────────────────────────────────────────────────────
    if sec.launches:
        lines += ["## New Launches", ""]
        for insight, raw in sec.launches:
            lines += _launch_block(insight, raw, _copy_for(picks, insight))

    # ── By Strategy Type ────────────────────────────────────────────────────────
    if any(sec.strategy.values()) or sec.quant_firms:
        lines += ["## By Strategy Type", ""]
        for bucket in _BUCKET_ORDER:
            bucket_rows = sec.strategy.get(bucket) or []
            if not bucket_rows:
                continue
            lines += [f"**{bucket}**", ""]
            for insight, raw in bucket_rows:
                clause = _copy_for(picks, insight) or _truncate_sentence(insight.trader_impact)
                lines += [_compact_line(insight, raw, bucket, clause), ""]
        if sec.quant_firms:
            lines += ["**From the Quant Firms**", ""]
            for insight, raw in sec.quant_firms:
                clause = _copy_for(picks, insight) or _truncate_sentence(insight.trader_impact)
                lines += [_compact_line(insight, raw, "Quant Firms", clause), ""]

    # ── What Changed for Traders (job postings excluded — a role isn't a trader capability) ──
    selected = sec.selected()
    what_changed = [(i, r) for i, r in selected if _item_type(i) != "hiring"]
    if what_changed:
        lines += ["## What Changed for Traders", ""]
        for insight, raw in what_changed:
            clause = _truncate_sentence(insight.trader_impact)
            lines += [f"[{_safe_title(raw)}]({raw.url}) — {clause}", ""]

    # ── Worth Trying ────────────────────────────────────────────────────────────
    by_id = {str(i.id): (i, r) for i, r in selected}
    worth: list[Row] = []
    for pid in worth_meta:  # editorial LLM's picks first (if they resolve to selected items)
        if pid in by_id and by_id[pid] not in worth:
            worth.append(by_id[pid])
    for row in sec.worth_trying:  # top up with the deterministic fallback
        if row not in worth and len(worth) < WORTH_TRYING_COUNT:
            worth.append(row)
    worth = worth[:WORTH_TRYING_COUNT]
    if worth:
        lines += ["## Worth Trying", ""]
        for n, (insight, raw) in enumerate(worth, 1):
            why = ""
            entry = worth_meta.get(str(insight.id))
            if isinstance(entry, dict) and isinstance(entry.get("why"), str):
                why = entry["why"].strip()
            why = why or _truncate_sentence(insight.trader_impact)
            lines += [f"**{n}.** [{_safe_title(raw)}]({raw.url}) — {why}", ""]

    # ── Watch List ──────────────────────────────────────────────────────────────
    if sec.watch_list:
        lines += ["## Watch List", ""]
        for insight, raw in sec.watch_list:
            clause = _copy_for(picks, insight) or _truncate_sentence(insight.trader_impact)
            lines += [
                _compact_line(insight, raw, "early stage", clause)
                + " (announced / beta / waitlist — flagged, not vetted)",
                "",
            ]

    # ── Now Hiring (quant / HFT roles, India + global) ──────────────────────────
    if sec.hiring:
        lines += ["## Now Hiring", ""]
        for insight, raw in sec.hiring:
            label = _job_location(raw) or ("India" if _region(insight) == "India" else "Hiring")
            clause = _copy_for(picks, insight) or _truncate_sentence(insight.technical_summary)
            lines += [_compact_line(insight, raw, label, clause), ""]

    # ── India Watch (only when there's material) ────────────────────────────────
    if sec.india:
        lines += ["## India Watch", ""]
        for insight, raw in sec.india:
            clause = _copy_for(picks, insight) or _truncate_sentence(insight.trader_impact)
            lines += [_compact_line(insight, raw, insight.category, clause), ""]

    lines += ["---", ""]
    lines.append("*Generated by Trading Alpha Engine. This is a publish-ready draft — review before sending.*")
    return "\n".join(lines).rstrip() + "\n"


def markdown_for_date(session: Session, day: date) -> str:
    """Render the brief for a date. Reads the persisted editorial payload — never calls the LLM."""
    rows = _rows_for_date(session, day)
    brief = repository.get_brief(session, day)
    return _render(day, rows, brief)


def write_newsletter(day: date | None = None) -> Path:
    """Render the given day's insights (default: today, UTC) and write the Markdown draft.

    This is the only place the LLM editorial pass runs: it selects the day's top picks, asks
    the provider cascade — in one call — for the theme, editor's note, and per-pick editorial
    copy, and persists them so later (live) API renders reuse them without an LLM call. If no
    provider is configured (or the call fails), the render falls back to the raw technical
    fields and a deterministic tagline.
    """
    # Lazy import: only the generation path needs the LLM layer (keeps the read API slim).
    from ..intelligence.provider import build_provider
    from .editorial import generate_editorial

    settings = get_settings()
    day = day or datetime.now(timezone.utc).date()
    init_db()  # ensure the DailyBrief table exists (idempotent) for the standalone CLI path

    with session_scope() as session:
        rows = _rows_for_date(session, day)
        if rows:
            sec = _select(rows)
            result = generate_editorial(sec, build_provider(settings))
            if result is not None:
                payload, model_used = result
                repository.upsert_brief(session, day, payload, model_used)
                logger.info(f"[newsletter] editorial for {day.isoformat()} via {model_used}")
        content = markdown_for_date(session, day)

    out_dir = settings.newsletter_path
    out_dir.mkdir(parents=True, exist_ok=True)
    path = out_dir / f"{day.isoformat()}.md"
    path.write_text(content, encoding="utf-8")
    logger.info(f"[newsletter] wrote {path}")
    return path
