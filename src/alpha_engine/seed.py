"""Seed the database with representative fake insights for demos / UI verification.

This does NOT call any LLM — it inserts realistic-looking rows so the API and frontend can
be exercised without ingestion or synthesis. Safe to run repeatedly (dedup on external_id).
"""

from __future__ import annotations

import json
import random
from datetime import datetime, timedelta, timezone

from loguru import logger

from .db import init_db, session_scope
from .models import Approach, Category, Insight, RawItem
from .storage import repository
from .ingestion.base import RawItemDraft

# (source, category, approaches, title, summary, trader_impact) — retail-trader tone.
_SAMPLES = [
    ("github", Category.INTRADAY_TRADING, [Approach.AGENTIC_AI, Approach.AUTOMATION],
     "[langchain-ai/langgraph] Durable AI agents that trade the whole session without losing their place",
     "A framework update lets you build an always-on AI agent that keeps its state through crashes and restarts, so it can watch the market and place trades all day.",
     "You could run a hands-off intraday bot that survives a laptop reboot mid-session instead of forgetting its open positions and plan."),
    ("github", Category.TECHNICAL_ANALYSIS, [Approach.MACHINE_LEARNING],
     "[microsoft/qlib] Free toolkit adds a model that ranks stocks by momentum, retrained automatically",
     "An open-source library added a machine-learning model that scores which stocks are likely to keep trending, and retrains itself on fresh data on a schedule.",
     "Gives a chart-based trader a ready-made momentum ranker to build a watchlist from, without coding the model or babysitting retraining."),
    ("rss", Category.SWING_TRADING, [Approach.MACHINE_LEARNING],
     "How one trader uses an ML screener to surface multi-day breakout setups",
     "A practitioner blog walks through a simple model that flags stocks setting up for multi-day breakouts and ranks them each evening.",
     "A repeatable nightly routine to find swing setups so you're not manually scanning hundreds of charts after the close."),
    ("mcp", Category.TECHNICAL_ANALYSIS, [Approach.INFRA_DATA],
     "[MCP] A plug-and-play market-data connector for AI charting bots",
     "A small server exposes live and historical price and order-book data as ready-made tools any AI assistant can call.",
     "Lets your trading copilot pull real-time quotes and indicators without wiring up a broker API yourself."),
    ("reddit", Category.TECHNICAL_ANALYSIS, [Approach.AUTOMATION],
     "[r/algotrading] A no-code breakout bot people are actually running on a broker API",
     "Thread shares a rules-based bot that buys confirmed breakouts and trails a stop, set up through a broker's API with no ML involved.",
     "A concrete template for automating a breakout strategy you already trade by hand, freeing you from watching the screen."),
    ("forum", Category.INTRADAY_TRADING, [Approach.AGENTIC_AI],
     "[QuantConnect Community] Using an AI copilot to write and backtest day-trading strategies from plain English",
     "Members show how an LLM assistant drafts, compiles, and backtests intraday strategies from a plain-English description.",
     "Shrinks the gap between a trade idea and a tested strategy — describe a day-trading setup and get runnable, backtested code."),
    ("github", Category.FUNDAMENTAL_ANALYSIS, [Approach.SENTIMENT_NEWS, Approach.MACHINE_LEARNING],
     "[open-source] An AI that reads earnings calls and flags what changed",
     "A tool ingests earnings-call transcripts and filings and summarizes tone shifts and notable changes versus prior quarters.",
     "Skim the signal from a company's report in seconds instead of reading the whole transcript before a fundamentals-driven trade."),
    ("rss", Category.MACRO_ANALYSIS, [Approach.MACHINE_LEARNING, Approach.RISK_SIZING],
     "A simple regime detector that tells you when to risk more (or less)",
     "A blog shows a lightweight model that labels the market as calm or stormy and scales position size to match.",
     "Trade macro conditions more deliberately — lean in during calm regimes and cut size before turbulence, on autopilot."),
]


def seed_demo(count: int = 24) -> int:
    """Insert up to ``count`` fake insights spread over recent days. Returns count created."""
    init_db()
    now = datetime.now(timezone.utc)
    created = 0

    with session_scope() as session:
        for i in range(count):
            src, cat, approaches, title, summ, impact = _SAMPLES[i % len(_SAMPLES)]
            draft = RawItemDraft(
                source=src,
                external_id=f"demo:{i}",
                url=f"https://example.com/demo/{i}",
                title=title,
                body=summ,
                author="demo",
                created_at=now - timedelta(days=i % 5, hours=i),
            )
            new = repository.save_raw(session, [draft])
            if not new:
                continue
            raw = new[0]
            raw.processed = True
            session.add(raw)
            insight = Insight(
                raw_item_id=raw.id,  # type: ignore[arg-type]
                relevance_score=random.choice([7, 8, 8, 9, 9, 10]),
                category=cat.value,
                approaches=json.dumps([a.value for a in approaches]),
                technical_summary=summ,
                trader_impact=impact,
                model_used="demo:seed",
                created_at=now - timedelta(days=i % 5, hours=i),
            )
            session.add(insight)
            created += 1

    logger.info(f"[seed] created {created} demo insight(s).")
    return created
