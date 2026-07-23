"""API routes: the insight feed (filterable) + meta + newsletters."""

from __future__ import annotations

from collections.abc import Iterator
from datetime import date, datetime, time

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func, or_
from sqlmodel import Session, select

from ..config import COMMUNITY_SOURCES
from ..db import get_engine
from ..models import Approach, Category, Insight, ItemType, RawItem, Region
from ..newsletter.generate import available_dates, markdown_for_date
from .schemas import InsightOut, InsightPage, MetaOut, NewsletterList, NewsletterOut, SourceHealthOut

router = APIRouter(prefix="/api")


def get_session() -> Iterator[Session]:
    with Session(get_engine()) as session:
        yield session


def _apply_filters(
    stmt,
    *,
    category: str | None,
    approach: str | None,
    item_type: str | None,
    exclude_item_type: str | None,
    region: str | None,
    min_score: int | None,
    source: str | None,
    stream: str | None,
    date_from: date | None,
    date_to: date | None,
    q: str | None,
):
    if category:
        stmt = stmt.where(Insight.category == category)
    if approach:
        # approaches is a JSON array string, e.g. ["Agentic AI"]; match the quoted token.
        stmt = stmt.where(Insight.approaches.contains(f'"{approach}"'))
    if item_type:
        # Accept a comma-separated list ("launch,funding") so one view can span item types.
        types = [t for t in item_type.split(",") if t]
        stmt = stmt.where(Insight.item_type.in_(types))
    if exclude_item_type:
        # Comma-separated list to hide from a view (e.g. the main feed hides venture item types,
        # which live only in the Launches tab).
        excluded = [t for t in exclude_item_type.split(",") if t]
        stmt = stmt.where(Insight.item_type.not_in(excluded))
    if region:
        stmt = stmt.where(Insight.region == region)
    if min_score is not None:
        stmt = stmt.where(Insight.relevance_score >= min_score)
    if source:
        stmt = stmt.where(RawItem.source == source)
    if stream == "community":
        stmt = stmt.where(RawItem.source.in_(COMMUNITY_SOURCES))
    elif stream == "alpha":
        stmt = stmt.where(RawItem.source.not_in(COMMUNITY_SOURCES))
    if date_from is not None:
        stmt = stmt.where(Insight.created_at >= datetime.combine(date_from, time.min))
    if date_to is not None:
        stmt = stmt.where(Insight.created_at <= datetime.combine(date_to, time.max))
    if q:
        like = f"%{q}%"
        stmt = stmt.where(
            or_(
                Insight.technical_summary.ilike(like),
                Insight.trader_impact.ilike(like),
                RawItem.title.ilike(like),
            )
        )
    return stmt


@router.get("/insights", response_model=InsightPage)
def list_insights(
    session: Session = Depends(get_session),
    category: str | None = Query(None),
    approach: str | None = Query(None),
    item_type: str | None = Query(None),
    exclude_item_type: str | None = Query(None),
    region: str | None = Query(None),
    min_score: int | None = Query(None, ge=1, le=10),
    source: str | None = Query(None),
    stream: str | None = Query(None, pattern="^(alpha|community)$"),
    date_from: date | None = Query(None),
    date_to: date | None = Query(None),
    q: str | None = Query(None, description="Search summary / impact / title"),
    sort: str = Query("score", pattern="^(score|date)$"),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
) -> InsightPage:
    filters = dict(
        category=category, approach=approach, item_type=item_type,
        exclude_item_type=exclude_item_type, region=region,
        min_score=min_score, source=source, stream=stream,
        date_from=date_from, date_to=date_to, q=q,
    )

    base = select(Insight, RawItem).join(RawItem, Insight.raw_item_id == RawItem.id)
    base = _apply_filters(base, **filters)

    count_stmt = _apply_filters(
        select(func.count()).select_from(Insight).join(RawItem, Insight.raw_item_id == RawItem.id),
        **filters,
    )
    total = session.exec(count_stmt).one()

    if sort == "date":
        base = base.order_by(Insight.created_at.desc())
    else:
        base = base.order_by(Insight.relevance_score.desc(), Insight.created_at.desc())

    rows = session.exec(base.offset((page - 1) * page_size).limit(page_size)).all()
    items = [InsightOut.from_row(insight, raw) for insight, raw in rows]
    return InsightPage(items=items, total=total, page=page, page_size=page_size)


@router.get("/insights/{insight_id}", response_model=InsightOut)
def get_insight(insight_id: int, session: Session = Depends(get_session)) -> InsightOut:
    row = session.exec(
        select(Insight, RawItem)
        .join(RawItem, Insight.raw_item_id == RawItem.id)
        .where(Insight.id == insight_id)
    ).first()
    if row is None:
        raise HTTPException(status_code=404, detail="Insight not found")
    return InsightOut.from_row(*row)


@router.get("/meta", response_model=MetaOut)
def meta(session: Session = Depends(get_session)) -> MetaOut:
    sources = list(
        session.exec(
            select(RawItem.source)
            .join(Insight, Insight.raw_item_id == RawItem.id)
            .distinct()
        )
    )
    score_min = session.exec(select(func.min(Insight.relevance_score))).one()
    score_max = session.exec(select(func.max(Insight.relevance_score))).one()
    total = session.exec(select(func.count()).select_from(Insight)).one()
    community_count = session.exec(
        select(func.count())
        .select_from(Insight)
        .join(RawItem, Insight.raw_item_id == RawItem.id)
        .where(RawItem.source.in_(COMMUNITY_SOURCES))
    ).one()
    dates = available_dates(session)
    return MetaOut(
        categories=[c.value for c in Category],
        approaches=[a.value for a in Approach],
        item_types=[t.value for t in ItemType],
        regions=[r.value for r in Region],
        sources=sorted(sources),
        score_min=score_min or 1,
        score_max=score_max or 10,
        date_min=(dates[-1] if dates else None),
        date_max=(dates[0] if dates else None),
        total_insights=total,
        alpha_count=total - community_count,
        community_count=community_count,
    )


@router.get("/source-health", response_model=list[SourceHealthOut])
def get_source_health(session: Session = Depends(get_session)) -> list[SourceHealthOut]:
    from ..storage.repository import source_health

    return [SourceHealthOut(**item) for item in source_health(session)]


@router.get("/newsletters", response_model=NewsletterList)
def list_newsletters(session: Session = Depends(get_session)) -> NewsletterList:
    return NewsletterList(dates=available_dates(session))


@router.get("/newsletters/{day}", response_model=NewsletterOut)
def get_newsletter(day: str, session: Session = Depends(get_session)) -> NewsletterOut:
    try:
        parsed = date.fromisoformat(day)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail="Invalid date (use YYYY-MM-DD)") from exc
    return NewsletterOut(date=day, markdown=markdown_for_date(session, parsed))
