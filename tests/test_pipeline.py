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


def test_careers_source_forced_to_hiring(temp_db):
    """A careers item is persisted as item_type=hiring even if the provider says otherwise."""
    with db.session_scope() as s:
        repository.save_raw(s, [
            RawItemDraft(source="careers", external_id="j1", url="u", title="KEEP Quant Researcher",
                         body="Location: Bengaluru"),
        ])
    run_synthesis(provider=CascadeProvider([FakeProvider()]))  # FakeProvider returns item_type default (tooling)
    with db.session_scope() as s:
        insight = s.exec(select(Insight)).one()
        assert insight.item_type == "hiring"
        assert insight.workflow_stage is None


def test_processing_cap_scores_newest_first(temp_db):
    import time
    with db.session_scope() as s:
        for n in range(5):
            repository.save_raw(s, [
                RawItemDraft(source="rss", external_id=f"KEEP-{n}", url="u", title=f"KEEP {n}", body="b"),
            ])
            time.sleep(0.01)  # ensure distinct fetched_at ordering
    # Cap to 2 → only the 2 newest unprocessed items get scored this run.
    stats = run_synthesis(provider=CascadeProvider([FakeProvider()]), limit=2)
    assert stats.considered == 2
    with db.session_scope() as s:
        processed = s.exec(select(RawItem).where(RawItem.processed == True)).all()  # noqa: E712
        assert {r.external_id for r in processed} == {"KEEP-3", "KEEP-4"}  # newest two


def test_prune_insights_keeps_top_n(temp_db):
    titles = ["Alpha charting tool", "Beta options screener", "Gamma data feed", "Delta risk engine"]
    with db.session_scope() as s:
        repository.save_raw(s, [
            RawItemDraft(source="rss", external_id=f"KEEP-{n}", url="u", title=t, body="b")
            for n, t in enumerate(titles)
        ])
    with db.session_scope() as s:
        raws = s.exec(select(RawItem)).all()
        for score, r in zip((10, 9, 8, 7), raws):
            s.add(Insight(raw_item_id=r.id, relevance_score=score, category="Technical Analysis",
                          technical_summary="t", trader_impact="i", model_used="x"))
    with db.session_scope() as s:
        deleted = repository.prune_insights(s, alpha_keep=2, community_keep=0)
    assert deleted == 2
    with db.session_scope() as s:
        scores = sorted(i.relevance_score for i in s.exec(select(Insight)).all())
        assert scores == [9, 10]  # the two highest survived
        assert len(s.exec(select(RawItem)).all()) == 4  # RawItems untouched (never re-scored)


def test_prune_collapses_duplicate_app_updates(temp_db):
    """Repeated updates of the same app (e.g. successive freqtrade releases) collapse to one."""
    items = [
        ("f3", "[freqtrade/freqtrade] release 2026.3 — 2026.3", 9),
        ("f6", "[freqtrade/freqtrade] release 2026.6 — 2026.6", 8),  # same app -> dropped
        ("lean", "[QuantConnect/Lean] release 3.1 — 3.1", 7),        # different app -> kept
    ]
    with db.session_scope() as s:
        repository.save_raw(s, [
            RawItemDraft(source="github", external_id=eid, url="u", title=t, body="b")
            for eid, t, _ in items
        ])
    with db.session_scope() as s:
        raws = {r.external_id: r for r in s.exec(select(RawItem)).all()}
        for eid, _, score in items:
            s.add(Insight(raw_item_id=raws[eid].id, relevance_score=score,
                          category="Technical Analysis", technical_summary="t",
                          trader_impact="i", model_used="x"))
    with db.session_scope() as s:
        repository.prune_insights(s, alpha_keep=40, community_keep=20)  # generous cap: only dedup acts
    with db.session_scope() as s:
        titles = sorted(r.title for i, r in
                        s.exec(select(Insight, RawItem).join(RawItem, Insight.raw_item_id == RawItem.id)).all())
        assert len(titles) == 2  # one freqtrade (the 9) + Lean
        assert any("freqtrade" in t and "2026.3" in t for t in titles)  # kept the higher-scored
        assert not any("2026.6" in t for t in titles)                   # dropped the duplicate


def test_relabel_recycled_launches_moves_release_cards_to_tooling(temp_db):
    """GitHub items and release/version-titled cards leave the launch facet; genuine new-venture
    launches stay put. Deterministic, no LLM."""
    items = [
        ("github", "[hummingbot/hummingbot] release v2.12.0", "launch"),      # github -> tooling
        ("rss", "[freqtrade releases] 2026.1", "launch"),                     # version title -> tooling
        ("rss", "Alpha exchange platform goes live", "launch"),               # genuine launch -> stays
        ("github", "[some/startup] private beta", "early_stage"),             # github -> tooling
    ]
    with db.session_scope() as s:
        repository.save_raw(s, [
            RawItemDraft(source=src, external_id=f"e{n}", url="u", title=t, body="b")
            for n, (src, t, _) in enumerate(items)
        ])
    with db.session_scope() as s:
        by_ext = {r.external_id: r for r in s.exec(select(RawItem)).all()}
        for n, (_, _, it) in enumerate(items):
            s.add(Insight(raw_item_id=by_ext[f"e{n}"].id, relevance_score=9, category="Technical Analysis",
                          item_type=it, region="Global", workflow_stage="Execution",
                          technical_summary="t", trader_impact="i", model_used="x"))
    with db.session_scope() as s:
        assert repository.relabel_recycled_launches(s) == 3
    with db.session_scope() as s:
        by_title = {r.title: i for i, r in
                    s.exec(select(Insight, RawItem).join(RawItem, Insight.raw_item_id == RawItem.id)).all()}
        assert by_title["[hummingbot/hummingbot] release v2.12.0"].item_type == "tooling"
        assert by_title["[freqtrade releases] 2026.1"].item_type == "tooling"
        assert by_title["[some/startup] private beta"].item_type == "tooling"
        assert by_title["Alpha exchange platform goes live"].item_type == "launch"  # genuine venture kept
        assert by_title["[hummingbot/hummingbot] release v2.12.0"].workflow_stage is None  # cleared
    with db.session_scope() as s:
        assert repository.relabel_recycled_launches(s) == 0  # idempotent


def test_prune_quota_keeps_facet_items_below_the_cap(temp_db):
    """A low-scored hiring item survives pruning when a hiring quota is set, even though it
    would be crowded out of the overall top-N by higher-scored launches."""
    launch_titles = ["Alpha exchange platform", "Beta broker feature", "Gamma execution engine"]
    with db.session_scope() as s:
        repository.save_raw(s, [
            RawItemDraft(source="rss", external_id=f"L{n}", url="u", title=t, body="b")
            for n, t in enumerate(launch_titles)
        ] + [RawItemDraft(source="careers", external_id="job1", url="u", title="[Graviton] Quant Researcher", body="b")])
    with db.session_scope() as s:
        by_ext = {r.external_id: r for r in s.exec(select(RawItem)).all()}
        for n in range(3):  # three launches score 10 — they fill the top-N
            s.add(Insight(raw_item_id=by_ext[f"L{n}"].id, relevance_score=10, category="Technical Analysis",
                          item_type="launch", region="Global", technical_summary="t", trader_impact="i", model_used="x"))
        s.add(Insight(raw_item_id=by_ext["job1"].id, relevance_score=7, category="Quant Firms",
                      item_type="hiring", region="India", technical_summary="t", trader_impact="i", model_used="x"))
    # Cap alpha to 3 (the launches) — without a quota the hiring item (score 7) would be pruned.
    with db.session_scope() as s:
        repository.prune_insights(s, alpha_keep=3, community_keep=0, quotas={"hiring": 1})
    with db.session_scope() as s:
        types = sorted(i.item_type for i in s.exec(select(Insight)).all())
        assert types == ["hiring", "launch", "launch", "launch"]  # 3 launches + the quota'd hiring


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
