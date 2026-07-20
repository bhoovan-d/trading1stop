"""One-time SQLite to PostgreSQL data migration."""

from __future__ import annotations

import sqlite3
from pathlib import Path

from sqlalchemy import text
from sqlmodel import Session, select

from .db import get_engine, init_db
from .models import DailyBrief, Insight, RawItem, SourceRegistry


TABLES = ("rawitem", "insight", "dailybrief")


def _rows(source: sqlite3.Connection, table: str) -> list[dict]:
    source.row_factory = sqlite3.Row
    return [dict(row) for row in source.execute(f"SELECT * FROM {table}")]


def migrate_sqlite(sqlite_path: Path) -> dict[str, int]:
    """Copy legacy data into the configured PostgreSQL database and validate counts.

    The source file is opened read-only and never modified, leaving it as a rollback backup.
    """
    if not sqlite_path.exists():
        raise FileNotFoundError(sqlite_path)
    init_db()
    source = sqlite3.connect(f"file:{sqlite_path.as_posix()}?mode=ro", uri=True)
    try:
        payload = {table: _rows(source, table) for table in TABLES}
    finally:
        source.close()

    engine = get_engine()
    with Session(engine) as session:
        existing = {
            "rawitem": session.exec(select(RawItem)).first(),
            "insight": session.exec(select(Insight)).first(),
            "dailybrief": session.exec(select(DailyBrief)).first(),
        }
        if any(existing.values()):
            raise RuntimeError("Target PostgreSQL database is not empty; refusing to merge a SQLite export.")
        for row in payload["rawitem"]:
            row.setdefault("source_key", f"adapter:{row['source']}")
            session.add(RawItem(**row))
        # Flush parents before adding children: SQLite permits a looser insert order,
        # while PostgreSQL correctly enforces Insight.raw_item_id immediately.
        session.flush()
        for row in payload["insight"]:
            session.add(Insight(**row))
        for row in payload["dailybrief"]:
            session.add(DailyBrief(**row))
        session.flush()
        # Build one registry row per resource without issuing a query for every raw item.
        known_keys = {row.source_key for row in session.exec(select(SourceRegistry.source_key)).all()}
        for item in session.exec(select(RawItem)).all():
            key = item.source_key or f"adapter:{item.source}"
            if key not in known_keys:
                session.add(SourceRegistry(source_key=key, adapter=item.source, name=key, status="active"))
                known_keys.add(key)
        session.commit()

    # Explicit IDs were imported, so PostgreSQL sequences must advance past them.
    if engine.dialect.name == "postgresql":
        with engine.begin() as conn:
            for table in TABLES:
                conn.execute(text(
                    f"SELECT setval(pg_get_serial_sequence('{table}', 'id'), "
                    f"COALESCE((SELECT MAX(id) FROM {table}), 1), true)"
                ))

    with Session(engine) as session:
        actual = {"rawitem": len(session.exec(select(RawItem)).all()),
                  "insight": len(session.exec(select(Insight)).all()),
                  "dailybrief": len(session.exec(select(DailyBrief)).all())}
    expected = {table: len(rows) for table, rows in payload.items()}
    if actual != expected:
        raise RuntimeError(f"Migration validation failed: expected {expected}, got {actual}")
    return actual
