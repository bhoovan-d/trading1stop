"""Top-level pipeline orchestration: ingest -> synthesize -> store -> newsletter."""

from __future__ import annotations

from loguru import logger

from .config import get_settings, get_sources
from .db import init_db, session_scope
from .ingestion.registry import build_sources
from .intelligence.synthesize import SynthesisStats, run_synthesis
from .newsletter.generate import write_newsletter
from .storage import repository


def ingest(only: list[str] | None = None) -> dict[str, int]:
    """Run the configured (or selected) sources; return new-item counts per source."""
    init_db()
    settings = get_settings()
    sources = get_sources()
    adapters = build_sources(settings, sources, only=only)
    counts: dict[str, int] = {}

    for adapter in adapters:
        try:
            drafts = list(adapter.fetch())
        except Exception as exc:  # noqa: BLE001 — one bad source must not sink the run
            logger.error(f"[ingest] source '{adapter.source}' failed: {exc}")
            with session_scope() as session:
                repository.record_adapter_failure(session, adapter.source)
            continue
        with session_scope() as session:
            new_items = repository.save_raw(session, drafts)
        counts[adapter.source] = counts.get(adapter.source, 0) + len(new_items)
        logger.info(f"[ingest] {adapter.source}: {len(new_items)} new / {len(drafts)} fetched")

    return counts


def run_pipeline(
    only: list[str] | None = None,
    skip_synthesis: bool = False,
    skip_newsletter: bool = False,
) -> dict:
    """Execute all four phases once. Returns a summary suitable for logging/JSON."""
    logger.info("=== pipeline run start ===")
    ingest_counts = ingest(only=only)

    stats = SynthesisStats()
    if not skip_synthesis:
        stats = run_synthesis()

    newsletter_path = None
    if not skip_newsletter:
        newsletter_path = str(write_newsletter())

    with session_scope() as session:
        suspended_sources = repository.suspend_low_signal_sources(session)

    summary = {
        "ingested": ingest_counts,
        "ingested_total": sum(ingest_counts.values()),
        "insights": stats.insights,
        "discarded": stats.discarded,
        "failed": stats.failed,
        "by_tier": stats.by_tier,
        "newsletter": newsletter_path,
        "suspended_sources": suspended_sources,
    }
    logger.info(f"=== pipeline run done === {summary}")
    return summary
