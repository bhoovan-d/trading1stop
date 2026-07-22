"""Persistence + dedup helpers over the SQLModel session."""

from __future__ import annotations

import json
from datetime import date, datetime, timedelta, timezone

from sqlalchemy import delete as sa_delete, func, update as sa_update
from sqlmodel import Session, select

from ..config import COMMUNITY_SOURCES
from ..ingestion.base import RawItemDraft
from ..models import DailyBrief, Insight, InsightExtraction, RawItem, SourceRegistry


def source_key_for(draft: RawItemDraft) -> str:
    return draft.source_key or f"adapter:{draft.source}"


def _registry_details(draft: RawItemDraft) -> tuple[str, str | None, str]:
    raw = draft.raw or {}
    target = raw.get("full_name") or raw.get("repo")
    return (
        str(target) if target else draft.title[:160],
        str(target) if target else None,
        "candidate" if raw.get("kind") == "github_repo_candidate" else "active",
    )


def touch_source(session: Session, draft: RawItemDraft) -> SourceRegistry:
    """Create/update the resource-level registry record for an ingested draft."""
    key = source_key_for(draft)
    now = datetime.now(timezone.utc)
    entry = session.exec(select(SourceRegistry).where(SourceRegistry.source_key == key)).first()
    if entry is None:
        name, target, status = _registry_details(draft)
        entry = SourceRegistry(source_key=key, adapter=draft.source, name=name, url=draft.url,
                               target=target, status=status, last_seen_at=now, last_fetched_at=now)
        session.add(entry)
    else:
        entry.last_seen_at = now
        entry.last_fetched_at = now
        if draft.url:
            entry.url = draft.url
        session.add(entry)
    return entry


def save_raw(session: Session, drafts: list[RawItemDraft]) -> list[RawItem]:
    """Insert only items whose (source, external_id) is not already stored.

    Returns the newly inserted RawItems (with ids populated). Existing items are skipped,
    which is how re-ingestion is prevented.
    """
    inserted: list[RawItem] = []
    seen: set[tuple[str, str]] = set()

    for draft in drafts:
        key = (draft.source, draft.external_id)
        if key in seen:
            continue
        seen.add(key)

        exists = session.exec(
            select(RawItem.id).where(
                RawItem.source == draft.source,
                RawItem.external_id == draft.external_id,
            )
        ).first()
        if exists is not None:
            touch_source(session, draft)
            continue

        touch_source(session, draft)

        item = RawItem(
            source=draft.source,
            source_key=source_key_for(draft),
            external_id=draft.external_id,
            url=draft.url,
            title=draft.title,
            body=draft.body,
            author=draft.author,
            created_at=draft.created_at,
            content_hash=draft.content_hash(),
            raw_json=json.dumps(draft.raw, default=str),
        )
        session.add(item)
        inserted.append(item)

    session.flush()  # assign primary keys
    return inserted


def record_qualification(session: Session, raw_item: RawItem) -> None:
    """Promote a candidate after three kept insights in the rolling 30-day window."""
    key = raw_item.source_key or f"adapter:{raw_item.source}"
    source = session.exec(select(SourceRegistry).where(SourceRegistry.source_key == key)).first()
    if source is None or source.status != "candidate":
        return
    cutoff = datetime.now(timezone.utc) - timedelta(days=30)
    qualifying = session.exec(
        select(func.count()).select_from(Insight).join(RawItem, Insight.raw_item_id == RawItem.id)
        .where(RawItem.source_key == key, Insight.created_at >= cutoff)
    ).one()
    if qualifying >= 3:
        source.status = "active"
        session.add(source)


def active_github_targets(session: Session) -> list[str]:
    rows = session.exec(
        select(SourceRegistry.target).where(
            SourceRegistry.status == "active", SourceRegistry.adapter.in_(["mcp", "github"]),
            SourceRegistry.target.is_not(None),
        )
    ).all()
    return [target for target in rows if target]


def source_health(session: Session) -> list[dict]:
    cutoff = datetime.now(timezone.utc) - timedelta(days=30)
    result: list[dict] = []
    for source in session.exec(select(SourceRegistry).order_by(SourceRegistry.status, SourceRegistry.name)).all():
        kept = session.exec(
            select(func.count()).select_from(Insight).join(RawItem, Insight.raw_item_id == RawItem.id)
            .where(RawItem.source_key == source.source_key, Insight.created_at >= cutoff)
        ).one()
        result.append({"source_key": source.source_key, "name": source.name, "adapter": source.adapter,
                       "status": source.status, "url": source.url, "qualifying_insights_30d": kept,
                       "failure_count": source.failure_count, "last_seen_at": source.last_seen_at})
    return result


def record_adapter_failure(session: Session, adapter: str) -> None:
    """Record a fetch failure without letting one adapter stop the pipeline."""
    for source in session.exec(select(SourceRegistry).where(SourceRegistry.adapter == adapter)).all():
        source.failure_count += 1
        session.add(source)


def suspend_low_signal_sources(session: Session, days: int = 30) -> int:
    """Suspend stale automatically discovered resources; curated sources remain active."""
    cutoff = datetime.now(timezone.utc) - timedelta(days=days)
    changed = 0
    for source in session.exec(
        select(SourceRegistry).where(SourceRegistry.status.in_(["candidate", "active"]))
    ).all():
        if not source.target or source.last_seen_at >= cutoff:
            continue
        source.status = "suspended"
        session.add(source)
        changed += 1
    return changed


def get_unprocessed(
    session: Session, limit: int | None = None, newest_first: bool = False
) -> list[RawItem]:
    order = RawItem.fetched_at.desc() if newest_first else RawItem.fetched_at
    stmt = select(RawItem).where(RawItem.processed == False).order_by(order)  # noqa: E712
    if limit is not None:
        stmt = stmt.limit(limit)
    return list(session.exec(stmt).all())


def mark_processed(session: Session, item: RawItem) -> None:
    # Bulk update by id rather than mutating the ORM object: during concurrent synthesis the
    # RawItem instances are detached (read from worker threads), so writing via a statement
    # keeps the session interaction entirely in the writer thread.
    session.execute(
        sa_update(RawItem).where(RawItem.id == item.id).values(processed=True)
    )


def reset_all_processed(session: Session) -> int:
    """Mark every RawItem unprocessed so synthesis re-scores the whole corpus. Returns the count."""
    result = session.execute(sa_update(RawItem).values(processed=False))
    return result.rowcount or 0


def save_insight(
    session: Session,
    raw_item: RawItem,
    extraction: InsightExtraction,
    model_used: str,
) -> Insight:
    # A careers item is definitionally a job posting: force item_type=hiring (and clear the
    # launch-only workflow_stage) regardless of what the LLM returned, so the /jobs view and the
    # newsletter's Now-Hiring section populate reliably across every provider.
    is_job = raw_item.source == "careers"
    item_type = "hiring" if is_job else extraction.item_type.value
    workflow_stage = None if is_job else (
        extraction.workflow_stage.value if extraction.workflow_stage else None
    )
    insight = Insight(
        raw_item_id=raw_item.id,  # type: ignore[arg-type]
        relevance_score=extraction.relevance_score,
        category=extraction.category.value,
        approaches=json.dumps([a.value for a in extraction.approaches]),
        item_type=item_type,
        region=extraction.region.value,
        workflow_stage=workflow_stage,
        technical_summary=extraction.technical_summary,
        trader_impact=extraction.trader_impact,
        model_used=model_used,
    )
    session.add(insight)
    return insight


def prune_insights(session: Session, alpha_keep: int, community_keep: int) -> int:
    """Keep only the top-N insights per stream (by score, then recency); delete the rest.

    Bounds what the site shows to a rolling "best of" window. Only ``Insight`` rows are removed —
    their ``RawItem`` stays ``processed=True``, so pruned items are never re-ingested or re-scored
    (no extra LLM cost). Returns the number of insights deleted.
    """
    deleted = 0
    for is_community, keep in ((False, alpha_keep), (True, community_keep)):

        def _stream(stmt):
            return stmt.where(
                RawItem.source.in_(COMMUNITY_SOURCES) if is_community
                else RawItem.source.not_in(COMMUNITY_SOURCES)
            )

        keep_ids = set(
            session.exec(
                _stream(select(Insight.id).join(RawItem, Insight.raw_item_id == RawItem.id))
                .order_by(Insight.relevance_score.desc(), Insight.created_at.desc())
                .limit(max(0, keep))
            ).all()
        )
        all_ids = set(
            session.exec(
                _stream(select(Insight.id).join(RawItem, Insight.raw_item_id == RawItem.id))
            ).all()
        )
        to_delete = all_ids - keep_ids
        if to_delete:
            session.execute(sa_delete(Insight).where(Insight.id.in_(to_delete)))
            deleted += len(to_delete)
    return deleted


def get_brief(session: Session, day: date) -> dict | None:
    """Return the stored editorial payload for a date, or None if none/invalid."""
    row = session.exec(
        select(DailyBrief).where(DailyBrief.brief_date == day.isoformat())
    ).first()
    if row is None:
        return None
    try:
        return json.loads(row.payload_json)
    except (json.JSONDecodeError, TypeError):
        return None


def upsert_brief(session: Session, day: date, payload: dict, model_used: str) -> None:
    """Insert or replace the editorial payload for a date (one row per date)."""
    payload_json = json.dumps(payload)
    row = session.exec(
        select(DailyBrief).where(DailyBrief.brief_date == day.isoformat())
    ).first()
    if row is None:
        session.add(
            DailyBrief(brief_date=day.isoformat(), payload_json=payload_json, model_used=model_used)
        )
    else:
        row.payload_json = payload_json
        row.model_used = model_used
        session.add(row)
