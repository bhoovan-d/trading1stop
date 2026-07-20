"""Newsletter selection + rendering tests — no DB, no LLM."""

from __future__ import annotations

import json
from datetime import date

from alpha_engine.models import Insight, RawItem
from alpha_engine.newsletter import generate as gen


def _row(
    iid: int,
    *,
    score: int = 8,
    category: str = "Technical Analysis",
    approaches: list[str] | None = None,
    item_type: str = "tooling",
    region: str = "Global",
    stage: str | None = None,
    source: str = "rss",
) -> gen.Row:
    insight = Insight(
        id=iid,
        raw_item_id=iid,
        relevance_score=score,
        category=category,
        approaches=json.dumps(approaches or []),
        item_type=item_type,
        region=region,
        workflow_stage=stage,
        technical_summary=f"Summary {iid}.",
        trader_impact=f"You can now do thing {iid}.",
    )
    raw = RawItem(id=iid, source=source, external_id=str(iid), url=f"https://x/{iid}", title=f"Item {iid}")
    return (insight, raw)


# ── strategy_bucket ──────────────────────────────────────────────────────────
def test_strategy_bucket_mapping():
    assert gen.strategy_bucket(_row(1, category="Technical Analysis")[0]) == "Technical"
    assert gen.strategy_bucket(_row(2, category="Intraday Trading")[0]) == "Technical"
    assert gen.strategy_bucket(_row(3, category="Swing Trading")[0]) == "Technical"
    assert gen.strategy_bucket(_row(4, category="Macro Analysis")[0]) == "Macro"
    assert gen.strategy_bucket(_row(5, category="Fundamental Analysis")[0]) == "Fundamental"


def test_sentiment_approach_wins_over_category():
    row = _row(1, category="Technical Analysis", approaches=["Sentiment & News"])
    assert gen.strategy_bucket(row[0]) == "Sentiment"


def test_quant_firms_has_no_strategy_bucket():
    assert gen.strategy_bucket(_row(1, category="Quant Firms")[0]) is None


# ── _select sectioning ───────────────────────────────────────────────────────
def test_sections_are_disjoint_and_prioritized():
    rows = [
        _row(1, item_type="early_stage", score=10),        # -> watch list
        _row(2, item_type="launch", score=9),              # -> launches
        _row(3, item_type="funding", score=9),             # -> launches
        _row(4, region="India", score=9),                  # -> india
        _row(5, category="Macro Analysis", score=8),       # -> strategy Macro
        _row(6, category="Quant Firms", score=8),          # -> quant firms sub-block
    ]
    sec = gen._select(rows)
    assert [i.id for i, _ in sec.watch_list] == [1]
    assert {i.id for i, _ in sec.launches} == {2, 3}
    assert [i.id for i, _ in sec.india] == [4]
    assert [i.id for i, _ in sec.strategy["Macro"]] == [5]
    assert [i.id for i, _ in sec.quant_firms] == [6]
    # every selected row appears exactly once
    ids = [i.id for i, _ in sec.selected()]
    assert sorted(ids) == [1, 2, 3, 4, 5, 6]
    assert len(ids) == len(set(ids))


def test_india_takes_priority_over_launch():
    # an India-region launch is concentrated in the India section, not New Launches
    rows = [_row(1, region="India", item_type="launch", score=9)]
    sec = gen._select(rows)
    assert [i.id for i, _ in sec.india] == [1]
    assert sec.launches == []


# ── _rows India community carve-out (query-level threshold) ──────────────────
def test_render_includes_all_sections():
    rows = [
        _row(1, item_type="launch", score=9, stage="Execution"),
        _row(2, item_type="early_stage", score=8),
        _row(3, region="India", category="Macro Analysis", score=8),
        _row(4, category="Fundamental Analysis", score=7),
    ]
    md = gen._render(date(2026, 7, 21), rows)
    assert "## New Launches" in md
    assert "## Watch List" in md
    assert "## India Watch" in md
    assert "## By Strategy Type" in md
    assert "## What Changed for Traders" in md
    assert "## Worth Trying" in md
    assert "**Touches:** Execution" in md
    assert "not vetted" in md


def test_india_section_omitted_when_empty():
    rows = [_row(1, item_type="launch", score=9)]
    md = gen._render(date(2026, 7, 21), rows)
    assert "## India Watch" not in md


def test_legacy_brief_payload_renders():
    # a pre-v2 payload (only theme/editor_note/picks, no worth_trying) must still render
    rows = [_row(1, item_type="launch", score=9), _row(2, category="Macro Analysis", score=8)]
    legacy = {"theme": "Old theme.", "editor_note": "Old note.", "picks": {"1": {"summary": "Editorial one."}}}
    md = gen._render(date(2026, 7, 21), rows, legacy)
    assert "*Old theme.*" in md
    assert "Old note." in md
    assert "Editorial one." in md  # per-pick copy still applied


def test_worth_trying_honors_editorial_picks():
    rows = [_row(1, item_type="launch", score=9), _row(2, item_type="launch", score=8)]
    brief = {"worth_trying": {"2": {"why": "Try this one first."}}}
    md = gen._render(date(2026, 7, 21), rows, brief)
    assert "Try this one first." in md


def test_no_qualifying_rows_message():
    md = gen._render(date(2026, 7, 21), [])
    assert "No qualifying insights" in md
