"""Demand signals: what traders keep asking for, distilled across community posts.

Every other part of the pipeline scores ONE item at a time. This one works the opposite way: it
hands the LLM a batch of recent community posts and asks which questions/frustrations recur. A
single "how do I automate NIFTY options?" thread is noise; twelve of them in a week is a product
opportunity — and that pattern only exists ACROSS items, so per-item scoring can never see it.

Reuses the freeform ``CascadeProvider.summarize`` seam that the newsletter editorial rides on.
"""

from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone

from loguru import logger
from sqlmodel import Session, select

from ..config import COMMUNITY_SOURCES, Settings, get_settings
from ..db import session_scope
from ..models import DemandSignal, RawItem, Region
from .provider import CascadeProvider, build_provider

SYSTEM_PROMPT = """\
You analyse what independent/retail traders are struggling with, reading raw posts from trading \
communities (r/algotrading, r/options, r/IndianStreetBets and similar).

Your job is NOT to summarise individual posts. It is to find the QUESTIONS AND FRUSTRATIONS THAT \
KEEP COMING UP — the same need voiced by different people in different words. Repeated demand with \
no good answer is a product opportunity, and that is the only thing worth reporting.

Rules:
- Group posts by the UNDERLYING NEED, not by wording. "Automating Bank Nifty entries", "broker API \
  for option orders" and "bot to place NIFTY spreads" are ONE signal about automating Indian \
  options, not three.
- Only report a signal backed by AT LEAST 2 different posts. Ignore one-off questions.
- Prefer concrete, technical needs a tool could actually solve (automation, data, execution, \
  backtesting, risk, broker APIs, tax/reporting) over vents, market calls, or "is X a good buy".
- Write `question` in the trader's own voice, as a real question, max ~12 words.
- `summary`: ONE plain sentence on what people are actually stuck on and why.
- `opportunity`: ONE sentence naming the gap — what doesn't exist, or what's too hard today.
- `region`: "India" if the need is specific to Indian markets/brokers (NSE, Nifty, Bank Nifty, \
  Zerodha, Upstox, Dhan, SEBI), otherwise "Global".
- Order signals by how often they recur, strongest first. Return at most 6. If nothing genuinely \
  recurs, return an empty list — say nothing rather than inventing a pattern.

Respond with a SINGLE JSON object and nothing else:
{"signals": [{"question": "...", "summary": "...", "opportunity": "...", "region": "India|Global", \
"post_ids": [1, 4, 9]}]}
`post_ids` must be the numeric ids of the posts that evidence the signal (at least 2)."""


def _strip_fences(text: str) -> str:
    t = text.strip()
    if t.startswith("```"):
        t = t.split("\n", 1)[-1] if "\n" in t else t[3:]
        if t.endswith("```"):
            t = t[:-3]
    return t.strip()


def build_prompt(items: list[RawItem]) -> str:
    """One line per post — id, community, title, and a short body snippet for context."""
    lines = ["Community posts from the last few days:", ""]
    for item in items:
        snippet = " ".join((item.body or "").split())[:220]
        lines.append(f"[{item.id}] {item.title}")
        if snippet:
            lines.append(f"     {snippet}")
    lines.append("")
    lines.append("Which needs recur across these posts? Return the JSON object.")
    return "\n".join(lines)


def _salvage_truncated(text: str) -> str | None:
    """Rescue a response the model ran out of tokens mid-way through.

    Free-tier models regularly hit the ceiling partway down the signal list. The signals already
    emitted are perfectly good, so rather than throw the whole batch away, close the JSON after the
    last COMPLETE signal object and parse that.
    """
    start = text.find('"signals"')
    if start == -1:
        return None
    end = text.rfind("}")
    while end > start:
        candidate = text[: end + 1] + "]}"
        try:
            json.loads(candidate)
            return candidate
        except (json.JSONDecodeError, TypeError):
            end = text.rfind("}", 0, end)
    return None


def parse_signals(text: str, by_id: dict[int, RawItem]) -> list[dict]:
    """Shared parser for both signal kinds (community demand and quant-firm trends).

    Both prompts return the same envelope, so both get the same guarantees: canonical fields,
    resolved evidence, and the >=2-items rule that keeps a "pattern" from resting on one item.
    """
    return _parse(text, by_id)


def _parse(text: str, by_id: dict[int, RawItem]) -> list[dict]:
    """Parse the model's signal list, keeping only entries with >=2 resolvable posts."""
    cleaned = _strip_fences(text)
    try:
        data = json.loads(cleaned)
    except (json.JSONDecodeError, TypeError):
        repaired = _salvage_truncated(cleaned)
        if repaired is None:
            logger.warning("[demand] non-JSON response.")
            return []
        logger.info("[demand] response was truncated — recovered the complete signals.")
        try:
            data = json.loads(repaired)
        except (json.JSONDecodeError, TypeError):
            return []
    raw_signals = data.get("signals") if isinstance(data, dict) else None
    if not isinstance(raw_signals, list):
        return []

    out: list[dict] = []
    for sig in raw_signals:
        if not isinstance(sig, dict):
            continue
        question = str(sig.get("question", "")).strip()
        if not question:
            continue
        ids = sig.get("post_ids")
        evidence = [
            {"title": by_id[i].title, "url": by_id[i].url}
            for i in (ids if isinstance(ids, list) else [])
            if isinstance(i, int) and i in by_id
        ]
        # The whole premise is "several people asked this" — a signal we can't evidence twice
        # isn't one, whatever the model claimed.
        if len(evidence) < 2:
            continue
        region = str(sig.get("region", "")).strip().lower()
        out.append({
            "question": question,
            "summary": str(sig.get("summary", "")).strip(),
            "opportunity": str(sig.get("opportunity", "")).strip(),
            "region": Region.INDIA.value if region == "india" else Region.GLOBAL.value,
            "evidence": evidence,
        })
    return out


def detect_demand_signals(
    settings: Settings | None = None,
    provider: CascadeProvider | None = None,
    days: int = 14,
    max_posts: int = 120,
) -> int:
    """Cluster recent community posts into recurring demand signals. Returns how many were stored.

    Replaces the previous window's signals wholesale — this is a rolling read of what people are
    asking now, not an archive.
    """
    settings = settings or get_settings()
    provider = provider or build_provider(settings)
    if not getattr(provider, "available", True):
        logger.warning("[demand] no LLM provider available — skipping.")
        return 0

    now = datetime.now(timezone.utc)
    cutoff = (now - timedelta(days=days)).replace(tzinfo=None)

    with session_scope() as session:
        items = list(session.exec(
            select(RawItem)
            .where(RawItem.source.in_(COMMUNITY_SOURCES))
            .where(RawItem.fetched_at >= cutoff)
            .order_by(RawItem.fetched_at.desc())
            .limit(max_posts)
        ).all())
        if len(items) < 4:
            logger.info(f"[demand] only {len(items)} community post(s) in window — skipping.")
            return 0
        by_id = {i.id: i for i in items if i.id is not None}
        session.expunge_all()

    logger.info(f"[demand] clustering {len(items)} community post(s) from the last {days}d…")
    result = provider.summarize(build_prompt(items), system=SYSTEM_PROMPT, max_tokens=3000)
    if result is None:
        logger.warning("[demand] provider returned nothing.")
        return 0

    signals = _parse(result[0], by_id)
    if not signals:
        logger.info("[demand] no recurring signal found — leaving existing ones untouched.")
        return 0

    with session_scope() as session:
        for old in session.exec(select(DemandSignal).where(DemandSignal.kind == "demand")).all():
            session.delete(old)
        for sig in signals:
            session.add(DemandSignal(
                kind="demand",
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
    logger.info(f"[demand] stored {len(signals)} demand signal(s).")
    return len(signals)
