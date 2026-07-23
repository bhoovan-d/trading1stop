"""Typer CLI entrypoint for the Trading Alpha Engine."""

from __future__ import annotations

from datetime import date, datetime
from pathlib import Path

import typer
from loguru import logger

from .config import get_settings
from .db import init_db
from .ingestion.registry import SOURCE_NAMES

app = typer.Typer(
    add_completion=False,
    help="Trading Alpha Engine — ingest, synthesize, and publish AI/ML-in-trading intelligence.",
)


@app.command("init-db")
def init_db_cmd() -> None:
    """Create the SQLite database and tables."""
    init_db()
    typer.echo("Initialized PostgreSQL schema from versioned migrations")


@app.command("migrate-sqlite")
def migrate_sqlite_cmd(
    sqlite_path: Path = typer.Argument(..., exists=True, readable=True),
) -> None:
    """Copy a legacy SQLite database to the configured empty PostgreSQL database."""
    from .migration import migrate_sqlite

    counts = migrate_sqlite(sqlite_path)
    typer.echo(f"Migrated and validated: {counts}. SQLite file retained at {sqlite_path}")


@app.command("source-health")
def source_health_cmd() -> None:
    """Show source status and recent qualifying-insight counts."""
    from .db import session_scope
    from .storage.repository import source_health

    with session_scope() as session:
        for item in source_health(session):
            typer.echo(item)


@app.command("relabel-launches")
def relabel_launches_cmd() -> None:
    """Move recycled release/version cards out of the Launches tab (launch/early_stage → tooling).

    Deterministic and LLM-free — fixes items mislabeled by the old "release"→launch mapping without
    re-scoring the corpus. Safe to re-run (idempotent); deletes nothing.
    """
    from .db import session_scope
    from .storage.repository import relabel_recycled_launches

    with session_scope() as session:
        changed = relabel_recycled_launches(session)
    typer.echo(f"Relabeled {changed} recycled launch card(s) -> tooling")


@app.command("ingest-only")
def ingest_only(
    source: list[str] = typer.Option(
        None, "--source", "-s", help=f"Restrict to specific sources: {', '.join(SOURCE_NAMES)}"
    ),
) -> None:
    """Fetch and store raw items only (no LLM calls)."""
    from .orchestrate import ingest

    counts = ingest(only=source or None)
    total = sum(counts.values())
    typer.echo(f"Ingested {total} new item(s): {counts}")


@app.command("synthesize")
def synthesize_cmd(
    workers: int = typer.Option(None, help="Concurrent LLM workers (default: SYNTHESIS_WORKERS)."),
    limit: int = typer.Option(None, help="Max items to process this run."),
) -> None:
    """Run only the AI synthesis phase over already-ingested, unprocessed items."""
    from .intelligence.synthesize import run_synthesis

    stats = run_synthesis(max_workers=workers, limit=limit)
    typer.echo(
        f"insights={stats.insights} discarded={stats.discarded} failed={stats.failed} "
        f"by_tier={stats.by_tier}"
    )


@app.command("reclassify")
def reclassify(
    workers: int = typer.Option(None, help="Concurrent LLM workers (default: SYNTHESIS_WORKERS)."),
    yes: bool = typer.Option(False, "--yes", "-y", help="Skip the confirmation prompt."),
) -> None:
    """Re-score EVERY ingested item under the current taxonomy/prompt.

    Clears all insights + daily briefs (recreating those tables so schema changes like the
    approaches column apply), resets every RawItem to unprocessed, then re-runs synthesis.
    Raw source content is preserved — no re-ingestion.
    """
    from .db import recreate_insight_tables, session_scope
    from .intelligence.synthesize import run_synthesis
    from .storage import repository

    init_db()
    if not yes:
        typer.confirm(
            "This deletes all existing insights + briefs and re-runs the LLM over every item. Continue?",
            abort=True,
        )

    recreate_insight_tables()
    with session_scope() as session:
        reset = repository.reset_all_processed(session)
    logger.info(f"[reclassify] reset {reset} item(s) to unprocessed; re-running synthesis…")

    stats = run_synthesis(max_workers=workers)
    typer.echo(
        f"reclassified: insights={stats.insights} discarded={stats.discarded} "
        f"failed={stats.failed} by_tier={stats.by_tier}"
    )


@app.command("gen-newsletter")
def gen_newsletter(
    day: str = typer.Option(None, "--date", help="Target date YYYY-MM-DD (default: today, UTC)."),
) -> None:
    """Render the newsletter draft for a date from stored insights."""
    from .newsletter.generate import write_newsletter

    target = date.fromisoformat(day) if day else None
    path = write_newsletter(target)
    typer.echo(f"Newsletter written to {path}")


@app.command("run-once")
def run_once(
    source: list[str] = typer.Option(None, "--source", "-s", help="Restrict ingestion sources."),
    skip_synthesis: bool = typer.Option(False, help="Skip the LLM synthesis phase."),
    skip_newsletter: bool = typer.Option(False, help="Skip newsletter generation."),
) -> None:
    """Run the full pipeline once: ingest -> synthesize -> store -> newsletter."""
    from .orchestrate import run_pipeline

    summary = run_pipeline(
        only=source or None,
        skip_synthesis=skip_synthesis,
        skip_newsletter=skip_newsletter,
    )
    typer.echo(summary)


@app.command("schedule")
def schedule(
    hours: float = typer.Option(24.0, help="Interval between pipeline runs, in hours."),
    run_now: bool = typer.Option(True, help="Run once immediately on start."),
) -> None:
    """Run the full pipeline on a recurring schedule (blocking daemon)."""
    from apscheduler.schedulers.blocking import BlockingScheduler

    from .orchestrate import run_pipeline

    scheduler = BlockingScheduler(timezone="UTC")
    kwargs = {"next_run_time": datetime.utcnow()} if run_now else {}
    scheduler.add_job(run_pipeline, "interval", hours=hours, id="pipeline", **kwargs)
    logger.info(f"Scheduler started — running every {hours}h. Ctrl-C to stop.")
    try:
        scheduler.start()
    except (KeyboardInterrupt, SystemExit):
        logger.info("Scheduler stopped.")


@app.command("seed-demo")
def seed_demo_cmd(
    count: int = typer.Option(24, help="How many demo insights to insert."),
) -> None:
    """Insert fake insights (no LLM) so the API/frontend can be exercised with data."""
    from .seed import seed_demo

    created = seed_demo(count)
    typer.echo(f"Seeded {created} demo insight(s).")


@app.command("serve")
def serve(
    host: str = typer.Option("127.0.0.1", help="Bind host."),
    port: int = typer.Option(8000, help="Bind port."),
    reload: bool = typer.Option(False, help="Auto-reload on code changes (dev)."),
) -> None:
    """Serve the JSON API (and the built SPA in production)."""
    import uvicorn

    init_db()
    uvicorn.run("alpha_engine.api.app:app", host=host, port=port, reload=reload)


if __name__ == "__main__":
    app()
