"""Post-quality rules: the noise patterns that were shipping as cards before.

Each test here corresponds to a real weak post observed on the live site. The prompt rules
themselves are model behaviour and can't be unit-tested, but the deterministic scaffolding around
them can — and that scaffolding is what makes the prompt rules reachable.
"""

from __future__ import annotations

import json

import pytest

from alpha_engine.intelligence.prompts import (
    JSON_INSTRUCTION,
    SYSTEM_PROMPT,
    build_user_prompt,
)
from alpha_engine.ingestion.github import _NOISE_COMMIT
from alpha_engine.models import RawItem


@pytest.mark.parametrize(
    "subject",
    [
        "chore: bump deps",
        "chore(deps): bump urllib3 from 2.0.7 to 2.2.1",
        "docs: fix typo in README",
        "test: add coverage for the parser",
        "ci: pin the runner image",
        "build(deps-dev): update vite",
        "style: reformat with black",
        "refactor!: split the client module",
        "perf: avoid a second pass",
        "CHORE: tidy up",  # prefix matching is case-insensitive
    ],
)
def test_housekeeping_commits_are_dropped_at_ingest(subject):
    assert _NOISE_COMMIT.match(subject)


@pytest.mark.parametrize(
    "subject",
    [
        "feat(etfs): release research-design front half",
        "fix(dataflows): make the Yahoo news window UTC and end-exclusive",
        "Add position grouping to the mobile app",
        "release v2.12.0",
        "fixture loading for the new backtester",  # 'fix' as a word, not a prefix
    ],
)
def test_feature_and_fix_commits_reach_the_model(subject):
    """`fix:`/`feat:` are the model's call — some fixes matter, and every feature might."""
    assert not _NOISE_COMMIT.match(subject)


def test_commit_kind_is_surfaced_to_the_model():
    """A one-line commit and a tagged release look identical once flattened to title+body."""
    item = RawItem(
        source="github", external_id="x", url="u",
        title="[TauricResearch/TradingAgents] fix(dataflows): make the news window UTC",
        body="fix(dataflows): make the news window UTC",
        raw_json=json.dumps({"repo": "TauricResearch/TradingAgents", "kind": "commit"}),
    )
    prompt = build_user_prompt(item)
    assert "KIND: commit" in prompt
    assert "not a release" in prompt


def test_release_kind_is_surfaced_to_the_model():
    item = RawItem(
        source="github", external_id="y", url="u", title="[freqtrade/freqtrade] release 2026.4",
        raw_json=json.dumps({"repo": "freqtrade/freqtrade", "kind": "release"}),
    )
    assert "KIND: release" in build_user_prompt(item)


@pytest.mark.parametrize("raw_json", [None, "", "not json", "[]", json.dumps({"repo": "a/b"})])
def test_missing_or_broken_kind_never_breaks_the_prompt(raw_json):
    """Most adapters record no kind at all; a malformed raw_json must not sink synthesis."""
    item = RawItem(source="reddit", external_id="z", url="u", title="t", raw_json=raw_json)
    prompt = build_user_prompt(item)
    assert "KIND:" not in prompt
    assert "TITLE: t" in prompt


def test_prompt_forbids_manufacturing_an_upside():
    """The old spec MANDATED a 'you can now…' line, so the model invented one for bug fixes and
    the flattering copy hid the weak item. Both halves of the fix must stay in the prompt."""
    assert "do NOT manufacture an upside" in SYSTEM_PROMPT
    assert "score the item 1-4" in SYSTEM_PROMPT
    # The JSON path hand-writes its own key specs, so a rule only in SYSTEM_PROMPT is applied
    # inconsistently across providers.
    assert "you can now" not in JSON_INSTRUCTION.lower()


@pytest.mark.parametrize(
    "phrase",
    ["Troubleshooting", "Polls and roundups", "Beginner questions", "Routine repository commits"],
)
def test_prompt_names_the_observed_noise_patterns(phrase):
    assert phrase in SYSTEM_PROMPT


def test_synthesis_reports_when_no_provider_is_configured():
    """A run that cannot score anything must be distinguishable from one with nothing to score.
    This exact silent no-op hid a dead pipeline behind green runs for two weeks."""
    from alpha_engine.intelligence.provider import CascadeProvider
    from alpha_engine.intelligence.synthesize import run_synthesis

    stats = run_synthesis(provider=CascadeProvider([]))
    assert stats.provider_available is False
    assert stats.insights == 0


def test_community_threshold_excludes_low_scoring_chatter():
    from alpha_engine.config import Settings

    # The two chit-chat cards on the live site scored 5 and 6.
    assert Settings().community_relevance_threshold == 6
