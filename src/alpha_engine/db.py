"""PostgreSQL engine, versioned schema setup, and session helper."""

from __future__ import annotations

import os
from collections.abc import Iterator
from contextlib import contextmanager

from sqlalchemy import inspect, text
from sqlalchemy.pool import NullPool
from sqlmodel import Session, SQLModel, create_engine

from .config import get_settings

# Import models so SQLModel.metadata is populated before create_all().
from . import models  # noqa: F401

_engine = None


def get_engine():
    global _engine
    if _engine is None:
        settings = get_settings()
        if not settings.database_url:
            raise RuntimeError("DATABASE_URL must point to PostgreSQL. Use migrate-sqlite before cutover.")
        db_url = settings.database_url
        if db_url.startswith("postgres://"):
            db_url = db_url.replace("postgres://", "postgresql://", 1)
        if not db_url.startswith("postgresql") and not db_url.startswith("sqlite"):
            raise RuntimeError("DATABASE_URL must use a PostgreSQL URL.")
        options = {"pool_pre_ping": True}
        if db_url.startswith("sqlite"):
            options["connect_args"] = {"check_same_thread": False}
        elif os.environ.get("VERCEL"):
            # On Vercel's serverless functions, don't hold a connection pool across invocations —
            # let Supabase's transaction pooler manage connections and open a fresh one per request.
            options["poolclass"] = NullPool
        _engine = create_engine(db_url, **options)
    return _engine


def init_db() -> None:
    """Apply idempotent schema migrations before the application uses the database."""
    engine = get_engine()
    SQLModel.metadata.create_all(engine)
    with engine.begin() as conn:
        conn.execute(text("CREATE TABLE IF NOT EXISTS schema_migrations (version INTEGER PRIMARY KEY)"))
        versions = {row[0] for row in conn.execute(text("SELECT version FROM schema_migrations"))}
        if 1 not in versions:
            conn.execute(text("INSERT INTO schema_migrations (version) VALUES (1)"))
        if 2 not in versions:
            columns = {column["name"] for column in inspect(conn).get_columns("rawitem")}
            if "source_key" not in columns:
                conn.execute(text("ALTER TABLE rawitem ADD COLUMN source_key VARCHAR NOT NULL DEFAULT ''"))
            conn.execute(text("CREATE INDEX IF NOT EXISTS ix_rawitem_source_key ON rawitem (source_key)"))
            conn.execute(text("INSERT INTO schema_migrations (version) VALUES (2)"))
        if 3 not in versions:
            # Backfill provenance/registry for databases created before source intelligence.
            conn.execute(text("UPDATE rawitem SET source_key = 'adapter:' || source WHERE source_key = ''"))
            conn.execute(text(
                "INSERT INTO sourceregistry "
                "(source_key, adapter, name, url, status, first_seen_at, last_seen_at, failure_count) "
                "SELECT DISTINCT r.source_key, r.source, r.source_key, '', 'active', CURRENT_TIMESTAMP, "
                "CURRENT_TIMESTAMP, 0 FROM rawitem r "
                "WHERE NOT EXISTS (SELECT 1 FROM sourceregistry s WHERE s.source_key = r.source_key)"
            ))
            conn.execute(text("INSERT INTO schema_migrations (version) VALUES (3)"))


def recreate_insight_tables() -> None:
    """Drop and recreate the Insight + DailyBrief tables.

    Used by ``reclassify`` to wipe derived data AND pick up schema changes (e.g. the new
    ``Insight.approaches`` column) — ``create_all`` never ALTERs an existing table, so a
    drop+create is how a column addition takes effect on an existing DB. ``RawItem`` (the
    ingested source content) is left untouched, so no re-ingestion is needed.
    """
    engine = get_engine()
    models.Insight.__table__.drop(engine, checkfirst=True)
    models.DailyBrief.__table__.drop(engine, checkfirst=True)
    SQLModel.metadata.create_all(engine)


@contextmanager
def session_scope() -> Iterator[Session]:
    """Transactional session context manager."""
    session = Session(get_engine())
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()
