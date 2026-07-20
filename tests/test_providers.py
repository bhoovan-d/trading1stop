"""OpenAICompatProvider parsing/normalization tests — stubbed client, no network."""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from alpha_engine.intelligence.openai_compat_provider import OpenAICompatProvider
from alpha_engine.models import Approach, Category, RawItem


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
