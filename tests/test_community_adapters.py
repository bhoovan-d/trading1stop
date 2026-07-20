"""Network-free tests for Phase 2 ingestion adapters."""

from __future__ import annotations

from types import SimpleNamespace

from alpha_engine.config import (
    BlueskySources,
    NumeraiSources,
    Settings,
    StockTwitsSources,
    Sources,
    stream_for,
)
from alpha_engine.ingestion.bluesky import BlueskySource
from alpha_engine.ingestion.numerai import NumeraiSource
from alpha_engine.ingestion.registry import build_sources
from alpha_engine.ingestion.stocktwits import StockTwitsSource


class _Response:
    def __init__(self, payload):
        self.payload = payload

    def raise_for_status(self):
        return None

    def json(self):
        return self.payload


def test_bluesky_deduplicates_posts_and_honors_global_cap(monkeypatch):
    post = {
        "uri": "at://did:plc:abc/app.bsky.feed.post/xyz",
        "cid": "cid",
        "record": {"text": "A portfolio optimization technique", "createdAt": "2026-07-18T10:00:00Z"},
        "author": {"handle": "quant.bsky.social"},
        "likeCount": 3,
    }
    monkeypatch.setattr("alpha_engine.ingestion.bluesky.httpx.get", lambda *_a, **_k: _Response({"posts": [post]}))
    source = BlueskySource(
        Settings(max_items_per_source=1), BlueskySources(queries=["quant finance", "portfolio optimization"])
    )

    items = list(source.fetch())

    assert len(items) == 1
    assert items[0].external_id == "bluesky:at://did:plc:abc/app.bsky.feed.post/xyz"
    assert items[0].url == "https://bsky.app/profile/quant.bsky.social/post/xyz"
    assert items[0].raw["query"] == "quant finance"


def test_numerai_emits_round_leaderboard_and_forum_items(monkeypatch):
    def fake_post(*_args, **_kwargs):
        return _Response(
            {"data": {"rounds": [{"number": 123, "openTime": "2026-07-18T00:00:00Z"}], "v2Leaderboard": [
                {"username": "model_a", "rank": 1, "reputation": 0.12, "stake": 100}
            ]}}
        )

    def fake_get(*_args, **_kwargs):
        return _Response({"topic_list": {"topics": [{"id": 42, "slug": "new-model", "title": "New model", "excerpt": "<p>Details</p>", "created_at": "2026-07-18T01:00:00Z"}]}})

    monkeypatch.setattr("alpha_engine.ingestion.numerai.httpx.post", fake_post)
    monkeypatch.setattr("alpha_engine.ingestion.numerai.httpx.get", fake_get)
    items = list(NumeraiSource(Settings(max_items_per_source=10), NumeraiSources()).fetch())

    assert {item.external_id for item in items} == {
        "numerai:round:123", "numerai:leaderboard:123:model_a", "numerai:forum:42"
    }
    assert next(item for item in items if item.external_id == "numerai:forum:42").body == "Details"


def test_stocktwits_skips_without_enablement_or_credentials():
    source = StockTwitsSource(Settings(), StockTwitsSources(enabled=True))
    assert list(source.fetch()) == []


def test_stocktwits_maps_bounded_stream_messages(monkeypatch):
    class _StreamResponse:
        def raise_for_status(self):
            return None

        def iter_lines(self):
            yield 'data: {"seq_id":"1","symbol":"SPY","metric":"message","created_at":"2026-07-18T10:00:00Z"}'
            yield 'data: {"seq_id":"2","symbol":"QQQ","metric":"message"}'

        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return False

    monkeypatch.setattr("alpha_engine.ingestion.stocktwits.httpx.stream", lambda *_a, **_k: _StreamResponse())
    source = StockTwitsSource(
        Settings(stocktwits_enabled=True, stocktwits_username="u", stocktwits_password="p", max_items_per_source=10),
        StockTwitsSources(enabled=True, symbols=["SPY"], max_messages=1),
    )

    items = list(source.fetch())

    assert len(items) == 1
    assert items[0].external_id == "stocktwits:1"
    assert items[0].title == "[$SPY] message"


def test_community_classification_and_registry_builders():
    assert stream_for("bluesky") == "community"
    assert stream_for("stocktwits") == "community"
    assert stream_for("numerai") == "alpha"

    sources = Sources(
        bluesky=BlueskySources(queries=["quant finance"]),
        numerai=NumeraiSources(),
        stocktwits=StockTwitsSources(),
    )
    built = build_sources(Settings(), sources, only=["bluesky", "numerai", "stocktwits"])
    assert [source.source for source in built] == ["bluesky", "numerai", "stocktwits"]
