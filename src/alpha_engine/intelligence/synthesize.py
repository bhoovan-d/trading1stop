"""Drive the LLM provider over unprocessed raw items, storing high-value insights."""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, field

from loguru import logger

from ..config import COMMUNITY_SOURCES, Settings, get_settings
from ..db import session_scope
from ..storage import repository
from .provider import CascadeProvider, build_provider


@dataclass
class SynthesisStats:
    considered: int = 0
    insights: int = 0
    discarded: int = 0
    failed: int = 0
    by_tier: dict[str, int] = field(default_factory=dict)


def run_synthesis(
    settings: Settings | None = None,
    provider: CascadeProvider | None = None,
    limit: int | None = None,
    max_workers: int | None = None,
) -> SynthesisStats:
    """Score + synthesize every unprocessed RawItem. Discards anything below the threshold.

    LLM calls are network-bound and rate-limited, so they run concurrently across a thread
    pool; the rotating cascade spreads that concurrency across all configured providers.
    Only the calling thread touches the DB session — worker threads read *detached* RawItems
    and return extractions, which the writer thread persists and commits one at a time.

    Items the provider cannot process (no provider, transient error, refusal) are left
    unprocessed so a later run can retry them.
    """
    settings = settings or get_settings()
    provider = provider or build_provider(settings)
    stats = SynthesisStats()

    if not getattr(provider, "available", True):
        logger.warning("[synthesis] no LLM provider available — skipping synthesis.")
        return stats

    alpha_threshold = settings.relevance_threshold
    community_threshold = settings.community_relevance_threshold

    def threshold_for(source: str) -> int:
        return community_threshold if source in COMMUNITY_SOURCES else alpha_threshold

    with session_scope() as session:
        # When a per-run cap is set, score the FRESHEST items first so the rolling best-of
        # window reflects current content (older leftovers are retried on later runs).
        items = repository.get_unprocessed(session, limit=limit, newest_first=limit is not None)
        if not items:
            logger.info("[synthesis] nothing to process.")
            return stats

        workers = max(1, min(max_workers or settings.synthesis_workers, len(items)))
        logger.info(f"[synthesis] {len(items)} item(s) to consider across {workers} worker(s).")

        # Detach the items so worker threads can read their (already-loaded) fields without
        # touching the session; all writes happen below in this thread.
        session.expunge_all()

        with ThreadPoolExecutor(max_workers=workers) as pool:
            futures = {pool.submit(provider.extract, item): item for item in items}
            for future in as_completed(futures):
                item = futures[future]
                stats.considered += 1
                try:
                    result = future.result()
                except Exception as exc:  # noqa: BLE001 — never let one item kill the batch
                    logger.warning(f"[synthesis] item {item.id} raised: {exc}")
                    result = None

                if result is None:
                    stats.failed += 1
                    continue  # leave unprocessed -> retried next run

                extraction, served_by = result
                stats.by_tier[served_by] = stats.by_tier.get(served_by, 0) + 1

                if extraction.relevance_score >= threshold_for(item.source):
                    repository.save_insight(session, item, extraction, model_used=served_by)
                    repository.record_qualification(session, item)
                    stats.insights += 1
                    logger.info(
                        f"[synthesis] KEEP {extraction.relevance_score}/10 "
                        f"[{extraction.category.value}] {item.title[:70]}"
                    )
                else:
                    stats.discarded += 1
                    logger.debug(
                        f"[synthesis] drop {extraction.relevance_score}/10 {item.title[:70]}"
                    )

                repository.mark_processed(session, item)
                # Commit per item, not once at the end: a run can process hundreds of items
                # across slow/rate-limited LLM calls, and a crash or kill partway through
                # must not roll back everything already scored.
                session.commit()

    logger.info(
        f"[synthesis] done: {stats.insights} kept, {stats.discarded} discarded, "
        f"{stats.failed} failed (of {stats.considered})."
    )
    return stats
