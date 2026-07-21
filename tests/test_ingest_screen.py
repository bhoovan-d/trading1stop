"""Ingest-time keyword screen tests — no network (feedparser stubbed)."""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from alpha_engine.config import RssFeed, RssSources, Settings
from alpha_engine.ingestion import rss as rss_mod
from alpha_engine.ingestion.base import matches_keywords
from alpha_engine.ingestion.rss import RssSource


# ── matches_keywords ─────────────────────────────────────────────────────────
def test_matches_keywords_hit_miss_and_empty():
    assert matches_keywords("An AI trading bot for the Nifty", ["ai", "forex"]) is True
    assert matches_keywords("Quarterly payments and lending update", ["trading", "ai"]) is False
    assert matches_keywords("anything", []) is True          # empty list -> pass-through
    assert matches_keywords("Case INSENSITIVE Match", ["insensitive"]) is True


# ── RSS screen ───────────────────────────────────────────────────────────────
_ENTRIES = [
    SimpleNamespace(title="An AI copilot for options trading", link="u1", id="1", summary="uses machine learning"),
    SimpleNamespace(title="Nifty ends higher as banks rally", link="u2", id="2", summary="market recap, no tech"),
    SimpleNamespace(title="New vegan restaurant opens downtown", link="u3", id="3", summary="totally off topic"),
]


def _source_for(screen: str | None, monkeypatch) -> RssSource:
    monkeypatch.setattr(rss_mod.time, "sleep", lambda *_: None)
    monkeypatch.setattr(
        rss_mod.feedparser, "parse",
        lambda _url: SimpleNamespace(bozo=0, entries=list(_ENTRIES)),
    )
    cfg = RssSources(feeds=[RssFeed(name="Test", url="http://x", screen=screen)])
    return RssSource(Settings(), cfg)


def _titles(source: RssSource) -> list[str]:
    return [d.title for d in source.fetch()]


def test_screen_ai_keeps_only_ai_items(monkeypatch):
    titles = _titles(_source_for("ai", monkeypatch))
    assert len(titles) == 1
    assert "AI copilot" in titles[0]


def test_screen_markets_keeps_markets_items(monkeypatch):
    titles = _titles(_source_for("markets", monkeypatch))
    # both the AI-trading item and the Nifty recap mention markets terms; restaurant is dropped
    assert len(titles) == 2
    assert all("restaurant" not in t for t in titles)


def test_no_screen_keeps_everything(monkeypatch):
    assert len(_titles(_source_for(None, monkeypatch))) == 3


def test_unknown_screen_mode_is_no_screen(monkeypatch):
    # a typo'd/unknown screen value must not silently drop everything
    assert len(_titles(_source_for("bogus", monkeypatch))) == 3
