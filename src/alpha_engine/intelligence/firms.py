"""Quant-firm signals: what top firms are building and hiring for, read as a trend.

A single job posting is a job posting. Eight ML-engineer roles opening across AlphaGrep, Graviton
and NK Securities in the same month is a statement about where the institutional edge is heading —
and that is what an outside trader can actually use. Raw postings live in /jobs; this module
produces the firm-level read that /quant-firms shows.

Shares the clustering shape (and parser) with :mod:`.demand` — same envelope, same >=2-evidence
rule, same truncation recovery.
"""

from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone

from loguru import logger
from sqlmodel import select

from ..config import Settings, get_settings
from ..db import session_scope
from ..models import DemandSignal, RawItem
from .demand import build_prompt, parse_signals
from .provider import CascadeProvider, build_provider

SYSTEM_PROMPT = """\
You read job postings and engineering signals from quantitative trading and HFT firms (Jane Street, \
Jump, DRW, IMC, Tower Research, Point72, WorldQuant, and Indian firms like Graviton, AlphaGrep, \
Quadeye, NK Securities).

Your job is NOT to summarise individual postings. It is to identify TRENDS ACROSS FIRMS — what these \
firms are collectively building, hiring for, and betting on. An independent trader can't work at \
these firms, but what the firms invest in is a leading indicator of where the edge is going.

Rules:
- Group postings by the UNDERLYING CAPABILITY being built, not by job title. "ML Researcher", \
  "AI Engineer" and "Quant Researcher (Deep Learning)" across three firms are ONE signal about AI \
  adoption, not three.
- Only report a trend backed by AT LEAST 2 different postings. Ignore one-off roles.
- Prefer trends that reveal DIRECTION: a new capability (AI/ML, low-latency FPGA, crypto/digital \
  assets, alternative data, a new asset class or region) over generic back-office hiring.
- `question`: the trend as a headline, max ~12 words, e.g. "Indian quant firms are hiring ML \
  engineers". State the trend, don't ask a question.
- `summary`: ONE plain sentence — which firms, what roles, what capability.
- `opportunity`: ONE sentence on what this means for an independent trader watching from outside.
- `region`: "India" if the trend is concentrated in Indian offices/firms, else "Global".
- Order by how many postings support the trend, strongest first. Return at most 6. If nothing \
  genuinely recurs, return an empty list rather than inventing a trend.

Respond with a SINGLE JSON object and nothing else:
{"signals": [{"question": "...", "summary": "...", "opportunity": "...", "region": "India|Global", \
"post_ids": [1, 4, 9]}]}
`post_ids` must be the numeric ids of the postings that evidence the trend (at least 2)."""


def detect_firm_signals(
    settings: Settings | None = None,
    provider: CascadeProvider | None = None,
    days: int = 60,
    max_posts: int = 120,
) -> int:
    """Cluster recent quant-firm postings into cross-firm trends. Returns how many were stored.

    Uses a wider window than demand signals (hiring moves slower than conversation) and replaces
    the previous window's firm signals wholesale.
    """
    settings = settings or get_settings()
    provider = provider or build_provider(settings)
    if not getattr(provider, "available", True):
        logger.warning("[firms] no LLM provider available — skipping.")
        return 0

    now = datetime.now(timezone.utc)
    cutoff = (now - timedelta(days=days)).replace(tzinfo=None)

    with session_scope() as session:
        items = list(session.exec(
            select(RawItem)
            .where(RawItem.source == "careers")
            .where(RawItem.fetched_at >= cutoff)
            .order_by(RawItem.fetched_at.desc())
            .limit(max_posts)
        ).all())
        if len(items) < 4:
            logger.info(f"[firms] only {len(items)} posting(s) in window — skipping.")
            return 0
        by_id = {i.id: i for i in items if i.id is not None}
        session.expunge_all()

    logger.info(f"[firms] clustering {len(items)} firm posting(s) from the last {days}d…")
    result = provider.summarize(build_prompt(items), system=SYSTEM_PROMPT, max_tokens=3000)
    if result is None:
        logger.warning("[firms] provider returned nothing.")
        return 0

    signals = parse_signals(result[0], by_id)
    if not signals:
        logger.info("[firms] no cross-firm trend found — leaving existing signals untouched.")
        return 0

    with session_scope() as session:
        for old in session.exec(select(DemandSignal).where(DemandSignal.kind == "firm")).all():
            session.delete(old)
        for sig in signals:
            session.add(DemandSignal(
                kind="firm",
                question=sig["question"],
                summary=sig["summary"],
                opportunity=sig["opportunity"],
                mention_count=len(sig["evidence"]),
                region=sig["region"],
                evidence_json=json.dumps(sig["evidence"]),
                period_start=cutoff,
                period_end=now.replace(tzinfo=None),
                model_used=result[1],
            ))
    logger.info(f"[firms] stored {len(signals)} firm signal(s).")
    return len(signals)
