"""OpenAICompatProvider parsing/normalization tests — stubbed client, no network."""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from alpha_engine.intelligence.openai_compat_provider import OpenAICompatProvider
from alpha_engine.models import Approach, Category, ItemType, RawItem, Region, WorkflowStage


def _provider_returning(content: str | None) -> OpenAICompatProvider:
    p = OpenAICompatProvider(label="fake:test", base_url="http://x", api_key="k", model="m")

    class _Completions:
        def create(self, **_kwargs):
            msg = SimpleNamespace(content=content)
            return SimpleNamespace(choices=[SimpleNamespace(message=msg)])

    p.client = SimpleNamespace(chat=SimpleNamespace(completions=_Completions()))  # type: ignore[assignment]
    return p


ITEM = RawItem(id=1, source="rss", external_id="x", url="u", title="t", body="b")


def test_parses_valid_json():
    p = _provider_returning(
        '{"relevance_score": 9, "category": "Intraday Trading", '
        '"approaches": ["Agentic AI", "Automation"], '
        '"technical_summary": "s", "trader_impact": "i"}'
    )
    out = p.extract(ITEM)
    assert out is not None
    assert out.relevance_score == 9
    assert out.category == Category.INTRADAY_TRADING
    assert out.approaches == [Approach.AGENTIC_AI, Approach.AUTOMATION]


def test_normalizes_category_case_and_clamps_score():
    p = _provider_returning(
        '{"relevance_score": 42, "category": "swing trading", '
        '"technical_summary": "s", "trader_impact": "i"}'
    )
    out = p.extract(ITEM)
    assert out is not None
    assert out.relevance_score == 10  # clamped
    assert out.category == Category.SWING_TRADING
    assert out.approaches == []  # missing approaches -> empty list


def test_normalizes_approaches_case_and_drops_unknowns():
    p = _provider_returning(
        '{"relevance_score": 8, "category": "Macro Analysis", '
        '"approaches": ["machine learning", "totally made up", "Risk & Sizing"], '
        '"technical_summary": "s", "trader_impact": "i"}'
    )
    out = p.extract(ITEM)
    assert out is not None
    # unknown dropped, known values normalized to canonical casing, order preserved
    assert out.approaches == [Approach.MACHINE_LEARNING, Approach.RISK_SIZING]


def test_strips_code_fences():
    p = _provider_returning(
        '```json\n{"relevance_score": 7, "category": "Technical Analysis", '
        '"technical_summary": "s", "trader_impact": "i"}\n```'
    )
    assert p.extract(ITEM) is not None


@pytest.mark.parametrize(
    "content",
    [
        None,                                   # empty response
        "not json at all",                      # unparseable
        '{"relevance_score": 8, "category": "Made Up", "technical_summary": "s", "trader_impact": "i"}',  # bad category
        '{"category": "Technical Analysis", "technical_summary": "s", "trader_impact": "i"}',  # missing score
    ],
)
def test_bad_responses_return_none(content):
    assert _provider_returning(content).extract(ITEM) is None


def test_parses_new_axes():
    p = _provider_returning(
        '{"relevance_score": 9, "category": "Macro Analysis", '
        '"item_type": "launch", "region": "India", "workflow_stage": "Signal Generation", '
        '"technical_summary": "s", "trader_impact": "i"}'
    )
    out = p.extract(ITEM)
    assert out is not None
    assert out.item_type == ItemType.LAUNCH
    assert out.region == Region.INDIA
    assert out.workflow_stage == WorkflowStage.SIGNAL


def test_new_axes_synonyms():
    # synonyms map to canonical values; early_stage is launch-ish so it keeps a workflow_stage
    p = _provider_returning(
        '{"relevance_score": 8, "category": "Technical Analysis", '
        '"item_type": "beta", "region": "indian", "workflow_stage": "Execution", '
        '"technical_summary": "s", "trader_impact": "i"}'
    )
    out = p.extract(ITEM)
    assert out is not None
    assert out.item_type == ItemType.EARLY_STAGE  # "beta" synonym
    assert out.region == Region.INDIA             # "indian" synonym
    assert out.workflow_stage == WorkflowStage.EXECUTION


def test_hiring_item_type_and_synonym():
    p = _provider_returning(
        '{"relevance_score": 8, "category": "Quant Firms", "item_type": "job posting", '
        '"technical_summary": "s", "trader_impact": "i"}'
    )
    out = p.extract(ITEM)
    assert out is not None
    assert out.item_type == ItemType.HIRING  # "job posting" synonym -> hiring


def test_workflow_stage_dropped_for_non_launch_item():
    # a research/tooling item never carries a workflow_stage even if the model emits one
    p = _provider_returning(
        '{"relevance_score": 8, "category": "Technical Analysis", '
        '"item_type": "research", "workflow_stage": "Execution", '
        '"technical_summary": "s", "trader_impact": "i"}'
    )
    out = p.extract(ITEM)
    assert out is not None
    assert out.item_type == ItemType.RESEARCH
    assert out.workflow_stage is None


def test_missing_new_axes_fall_back_without_dropping():
    # No item_type/region at all: alpha source -> tooling/Global, item still kept.
    p = _provider_returning(
        '{"relevance_score": 7, "category": "Technical Analysis", '
        '"technical_summary": "s", "trader_impact": "i"}'
    )
    out = p.extract(ITEM)  # ITEM.source == "rss" (alpha)
    assert out is not None
    assert out.item_type == ItemType.TOOLING
    assert out.region == Region.GLOBAL
    assert out.workflow_stage is None


def test_community_source_unknown_item_type_becomes_discussion():
    community_item = RawItem(id=2, source="reddit", external_id="x", url="u", title="t", body="b")
    p = _provider_returning(
        '{"relevance_score": 7, "category": "Technical Analysis", '
        '"item_type": "nonsense", "technical_summary": "s", "trader_impact": "i"}'
    )
    out = p.extract(community_item)
    assert out is not None
    assert out.item_type == ItemType.DISCUSSION
