"""Render the daily newsletter — a curated, tiered brief — from stored insights."""

from __future__ import annotations

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

# How many insights fill each tier of the brief. Everything beyond these caps is intentionally
# left out of the newsletter — it still lives in the browsable feed.
LEAD_COUNT = 1
NOTABLE_COUNT = 3
IN_BRIEF_COUNT = 6
_TOP_COUNT = LEAD_COUNT + NOTABLE_COUNT

Row = tuple[Insight, RawItem]


def _as_date(dt: datetime | None) -> date | None:
    if dt is None:
        return None
    if dt.tzinfo is not None:
        dt = dt.astimezone(timezone.utc)
    return dt.date()


def _rows(session: Session) -> list[Row]:
    # The published brief is the high-signal ALPHA stream only; community discussion
    # (reddit/forums) is browse-only in the UI and deliberately excluded here.
    stmt = (
        select(Insight, RawItem)
        .join(RawItem, Insight.raw_item_id == RawItem.id)
        .where(RawItem.source.not_in(COMMUNITY_SOURCES))
        .order_by(Insight.relevance_score.desc(), Insight.created_at.desc())
    )
    return list(session.exec(stmt).all())


def _rows_for_date(session: Session, day: date) -> list[Row]:
    return [(i, r) for i, r in _rows(session) if _as_date(i.created_at) == day]


def available_dates(session: Session) -> list[str]:
    dates = {_as_date(i.created_at) for i in session.exec(select(Insight)).all()}
    return sorted((d.isoformat() for d in dates if d is not None), reverse=True)


def _select(rows: list[Row]) -> tuple[list[Row], list[Row], list[Row]]:
    """Split rows into (lead, notable, in_brief).

    ``rows`` arrive sorted by relevance_score desc. The Lead + Notable set is built by
    round-robin across categories — ordering the category cycle by each category's top score
    keeps the single highest-signal item as the Lead while maximizing category spread across
    the top picks. In Brief then takes the next-highest remaining items by pure score.
    """
    groups: dict[str, list[Row]] = {}
    for pair in rows:
        groups.setdefault(pair[0].category, []).append(pair)

    # Highest-signal category first, so the very first pick is the global top-scored item.
    cat_order = sorted(groups, key=lambda c: groups[c][0][0].relevance_score, reverse=True)
    queues = {c: list(groups[c]) for c in cat_order}

    top: list[Row] = []
    while len(top) < _TOP_COUNT and any(queues[c] for c in cat_order):
        for c in cat_order:
            if queues[c]:
                top.append(queues[c].pop(0))
                if len(top) >= _TOP_COUNT:
                    break

    picked = {id(pair) for pair in top}
    lead = top[:LEAD_COUNT]
    notable = top[LEAD_COUNT:_TOP_COUNT]
    in_brief = [p for p in rows if id(p) not in picked][:IN_BRIEF_COUNT]
    return lead, notable, in_brief


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


def _lead_block(insight: Insight, raw: RawItem, copy: str | None) -> list[str]:
    header = f"### {insight.relevance_score}/10 · [{_safe_title(raw)}]({raw.url})"
    if copy:  # editorial prose stands on its own — no raw technical dump
        body = [copy, ""]
    else:     # fallback: the original technical summary + why-it-matters
        body = [
            insight.technical_summary.strip(),
            "",
            f"**Why it matters:** {insight.trader_impact.strip()}",
            "",
        ]
    return [header, "", *body, _source_footer(raw), ""]


def _notable_block(insight: Insight, raw: RawItem, copy: str | None) -> list[str]:
    header = f"### {insight.relevance_score}/10 · [{_safe_title(raw)}]({raw.url})"
    line = copy if copy else f"**Why it matters:** {insight.trader_impact.strip()}"
    return [header, "", line, "", _source_footer(raw), ""]


def _render(day: date, rows: list[Row], brief: dict | None = None) -> str:
    title = f"# Trading Alpha Brief — {day.isoformat()}"
    if not rows:
        return f"{title}\n\n_No qualifying insights for this date._\n"

    lead, notable, in_brief = _select(rows)
    brief = brief or {}
    picks = brief.get("picks", {}) if isinstance(brief.get("picks"), dict) else {}

    intro = brief.get("theme") or (
        f"The sharpest AI/ML-in-trading developments surfaced today — {len(rows)} picks."
    )
    lines = [title, "", f"*{intro}*", ""]

    editor_note = brief.get("editor_note")
    if isinstance(editor_note, str) and editor_note.strip():
        lines += [editor_note.strip(), ""]

    lines.append("## The Lead")
    lines.append("")
    for insight, raw in lead:
        lines += _lead_block(insight, raw, _copy_for(picks, insight))

    if notable:
        lines.append("## Also Notable")
        lines.append("")
        for insight, raw in notable:
            lines += _notable_block(insight, raw, _copy_for(picks, insight))

    if in_brief:
        lines.append("## In Brief")
        lines.append("")
        for insight, raw in in_brief:
            clause = _copy_for(picks, insight) or _truncate_sentence(insight.trader_impact)
            lines.append(
                f"**{insight.relevance_score}/10** · {insight.category} · "
                f"[{_safe_title(raw)}]({raw.url}) — {clause}"
            )
            lines.append("")

    lines.append("---")
    lines.append("")
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
            lead, notable, in_brief = _select(rows)
            result = generate_editorial(lead, notable, in_brief, build_provider(settings))
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
