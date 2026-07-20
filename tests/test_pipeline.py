"""Pipeline logic tests with a fake LLM provider — no network, no API spend."""

from __future__ import annotations

import importlib

import pytest

from alpha_engine import config, db
from alpha_engine.ingestion.base import RawItemDraft
from alpha_engine.intelligence.provider import CascadeProvider
from alpha_engine.intelligence.synthesize import run_synthesis
from alpha_engine.models import Approach, Category, InsightExtraction, Insight, RawItem, SourceRegistry
from alpha_engine.storage import repository
from sqlmodel import select


@pytest.fixture()
def temp_db(tmp_path, monkeypatch):
    """Point the engine at a throwaway SQLite file and reset cached singletons."""
    monkeypatch.setenv("DB_PATH", str(tmp_path / "test.db"))
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{tmp_path / 'test.db'}")
    monkeypatch.setenv("RELEVANCE_THRESHOLD", "7")
    config.get_settings.cache_clear()
    config.get_sources.cache_clear()
    db._engine = None
    db.init_db()
    yield
    db._engine = None
    config.get_settings.cache_clear()


class FakeProvider:
    """Deterministic stand-in: high score if the title says KEEP, low if DROP."""

    label = "fake:test"

    def extract(self, item: RawItem) -> InsightExtraction | None:
        if "SKIP" in item.title:
            return None  # simulate a refusal / transient failure
        score = 9 if "KEEP" in item.title else 3
        return InsightExtraction(
            relevance_score=score,
            category=Category.INTRADAY_TRADING,
            approaches=[Approach.AGENTIC_AI],
            technical_summary="Fake summary.",
            trader_impact="Fake impact.",
        )


def _drafts():
    return [
        RawItemDraft(source="t", external_id="a", url="u", title="KEEP one", body="b"),
        RawItemDraft(source="t", external_id="b", url="u", title="DROP two", body="b"),
        RawItemDraft(source="t", external_id="c", url="u", title="SKIP three", body="b"),
    ]


def test_dedup(temp_db):
    with db.session_scope() as s:
        assert len(repository.save_raw(s, _drafts())) == 3
    with db.session_scope() as s:
        assert len(repository.save_raw(s, _drafts())) == 0  # re-ingestion is a no-op


def test_synthesis_threshold_and_processing(temp_db):
    with db.session_scope() as s:
        repository.save_raw(s, _drafts())

    provider = CascadeProvider([FakeProvider()])
    stats = run_synthesis(provider=provider)

    assert stats.insights == 1      # only KEEP survives the >=7 threshold
    assert stats.discarded == 1     # DROP scored 3
    assert stats.failed == 1        # SKIP returned None
    assert stats.by_tier == {"fake:test": 2}

    with db.session_scope() as s:
        insights = s.exec(select(Insight)).all()
        assert len(insights) == 1
        assert insights[0].relevance_score == 9
        assert insights[0].model_used == "fake:test"

        # KEEP + DROP marked processed; SKIP (failed) left for retry.
        unprocessed = s.exec(select(RawItem).where(RawItem.processed == False)).all()  # noqa: E712
        assert {i.title for i in unprocessed} == {"SKIP three"}


def test_empty_cascade_is_safe(temp_db):
    with db.session_scope() as s:
        repository.save_raw(s, _drafts())
    stats = run_synthesis(provider=CascadeProvider([]))  # no providers
    assert stats.insights == 0 and stats.considered == 0


def test_approaches_persisted_as_json(temp_db):
    import json

    with db.session_scope() as s:
        repository.save_raw(s, _drafts())
    run_synthesis(provider=CascadeProvider([FakeProvider()]))

    with db.session_scope() as s:
        insight = s.exec(select(Insight)).one()
        assert json.loads(insight.approaches) == [Approach.AGENTIC_AI.value]


def test_reclassify_reset_reprocesses_everything(temp_db):
    from alpha_engine.db import recreate_insight_tables

    with db.session_scope() as s:
        repository.save_raw(s, _drafts())
    run_synthesis(provider=CascadeProvider([FakeProvider()]))

    with db.session_scope() as s:
        assert len(s.exec(select(Insight)).all()) == 1
        # KEEP + DROP were processed; only SKIP remains unprocessed.
        assert len(s.exec(select(RawItem).where(RawItem.processed == False)).all()) == 1  # noqa: E712

    # Reclassify: wipe insights + reset every item to unprocessed.
    recreate_insight_tables()
    with db.session_scope() as s:
        n = repository.reset_all_processed(s)
    assert n == 3

    with db.session_scope() as s:
        assert s.exec(select(Insight)).all() == []
        assert len(s.exec(select(RawItem).where(RawItem.processed == False)).all()) == 3  # noqa: E712


def test_discovered_source_promotes_after_three_qualifying_insights(temp_db):
    drafts = [
        RawItemDraft(
            source="mcp", source_key="github:example/market-tool", external_id=f"candidate-{n}",
            url="https://github.com/example/market-tool", title=f"KEEP candidate {n}",
            raw={"kind": "github_repo_candidate", "full_name": "example/market-tool"},
        )
        for n in range(3)
    ]
    with db.session_scope() as s:
        repository.save_raw(s, drafts)
        assert s.exec(select(SourceRegistry)).one().status == "candidate"

    run_synthesis(provider=CascadeProvider([FakeProvider()]))

    with db.session_scope() as s:
        source = s.exec(select(SourceRegistry)).one()
        assert source.status == "active"
        health = repository.source_health(s)
        assert health[0]["qualifying_insights_30d"] == 3
