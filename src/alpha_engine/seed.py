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
from .models import Approach, Category, Insight, ItemType, RawItem, Region, WorkflowStage
from .storage import repository
from .ingestion.base import RawItemDraft

# (source, category, approaches, item_type, region, workflow_stage, title, summary, trader_impact)
# — everyday-trader tone; covers every newsletter section (launch / funding / early_stage / India).
_SAMPLES = [
    ("github", Category.INTRADAY_TRADING, [Approach.AGENTIC_AI, Approach.AUTOMATION],
     ItemType.TOOLING, Region.GLOBAL, None,
     "[langchain-ai/langgraph] Durable AI agents that trade the whole session without losing their place",
     "A framework update lets you build an always-on AI agent that keeps its state through crashes and restarts, so it can watch the market and place trades all day.",
     "You can now run a hands-off intraday bot that survives a laptop reboot mid-session instead of forgetting its open positions and plan."),
    ("rss", Category.TECHNICAL_ANALYSIS, [Approach.AUTOMATION, Approach.INFRA_DATA],
     ItemType.LAUNCH, Region.GLOBAL, WorkflowStage.EXECUTION,
     "TradeCopilot launches an AI charting assistant that turns plain-English setups into live alerts",
     "A new web app lets you describe a chart setup in ordinary words and it watches the market and pings you the moment the pattern appears.",
     "You can now get alerted on your own custom setups without coding a scanner or staring at charts all day."),
    ("rss", Category.QUANT_FIRMS, [Approach.INFRA_DATA, Approach.MACHINE_LEARNING],
     ItemType.FUNDING, Region.GLOBAL, WorkflowStage.SIGNAL,
     "AI trading-signal startup Alphaform raises $18M to open its data platform to retail traders",
     "A startup that builds AI-generated trade signals raised new funding and says it will open a lower-cost tier for individual traders.",
     "You can soon access institution-style AI signals on a retail budget instead of being priced out."),
    ("rss", Category.SWING_TRADING, [Approach.MACHINE_LEARNING],
     ItemType.EARLY_STAGE, Region.GLOBAL, WorkflowStage.RESEARCH,
     "SwingScout opens a waitlist for an AI screener that explains why each setup made the list",
     "An early-access tool ranks multi-day breakout candidates each evening and writes a short plain-English reason for every pick.",
     "You can soon get a nightly shortlist of swing setups with the 'why' spelled out, instead of trusting a black-box score."),
    ("reddit", Category.INTRADAY_TRADING, [Approach.AUTOMATION, Approach.AGENTIC_AI],
     ItemType.DISCUSSION, Region.INDIA, None,
     "[r/IndianStreetBets] How I automate Bank Nifty options intraday with an AI bot on Zerodha Kite",
     "An Indian retail trader shares how they wired an AI assistant to the Zerodha Kite API to place and manage Bank Nifty options trades during the day.",
     "You can now copy a concrete, India-specific setup for automating index-options day trades through a broker most Indian traders already use."),
    ("rss", Category.MACRO_ANALYSIS, [Approach.SENTIMENT_NEWS],
     ItemType.LAUNCH, Region.INDIA, WorkflowStage.SIGNAL,
     "Indian fintech ships an AI tool that reads RBI statements and flags rate-move odds",
     "A new tool summarizes Reserve Bank of India policy statements and estimates how likely a rate change is, in plain language.",
     "You can now gauge how India's central bank might move rates in minutes instead of reading the full policy text yourself."),
    ("github", Category.FUNDAMENTAL_ANALYSIS, [Approach.SENTIMENT_NEWS],
     ItemType.TOOLING, Region.GLOBAL, None,
     "[open-source] An AI that reads earnings calls and flags what changed",
     "A tool ingests earnings-call transcripts and filings and summarizes tone shifts and notable changes versus the prior quarter.",
     "You can now skim the signal from a company's report in seconds instead of reading the whole transcript before a fundamentals trade."),
    ("mcp", Category.TECHNICAL_ANALYSIS, [Approach.INFRA_DATA],
     ItemType.TOOLING, Region.GLOBAL, None,
     "[MCP] A plug-and-play market-data connector for AI charting bots",
     "A small server exposes live and historical price and order-book data as ready-made tools any AI assistant can call.",
     "You can now let your trading copilot pull real-time quotes and indicators without wiring up a broker API yourself."),
]


def seed_demo(count: int = 24) -> int:
    """Insert up to ``count`` fake insights spread over recent days. Returns count created."""
    init_db()
    now = datetime.now(timezone.utc)
    created = 0

    with session_scope() as session:
        for i in range(count):
            src, cat, approaches, item_type, region, stage, title, summ, impact = _SAMPLES[i % len(_SAMPLES)]
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
                item_type=item_type.value,
                region=region.value,
                workflow_stage=stage.value if stage else None,
                technical_summary=summ,
                trader_impact=impact,
                model_used="demo:seed",
                created_at=now - timedelta(days=i % 5, hours=i),
            )
            session.add(insight)
            created += 1

    logger.info(f"[seed] created {created} demo insight(s).")
    return created
