"""Network-free tests for the quant-firm careers (ATS) ingestion adapter."""

from __future__ import annotations

from alpha_engine.config import CareerBoard, CareersSources, Settings, Sources, stream_for
from alpha_engine.ingestion.careers import CareersSource
from alpha_engine.ingestion.registry import build_sources


class _Response:
    def __init__(self, payload):
        self.payload = payload

    def raise_for_status(self):
        return None

    def json(self):
        return self.payload


def test_greenhouse_jobs_map_to_drafts_with_stable_ids(monkeypatch):
    payload = {
        "jobs": [
            {
                "id": 12345,
                "title": "Quantitative Researcher — Systematic Equities",
                "absolute_url": "https://boards.greenhouse.io/janestreet/jobs/12345",
                "updated_at": "2026-07-18T10:00:00Z",
                # Greenhouse returns HTML-*escaped* content, as the live API does.
                "content": "&lt;h3&gt;About&lt;/h3&gt;&lt;p&gt;Build alpha models with &amp; deploy them.&lt;/p&gt;",
                "location": {"name": "New York"},
                "departments": [{"name": "Research"}],
            }
        ]
    }
    monkeypatch.setattr(
        "alpha_engine.ingestion.careers.httpx.get", lambda *_a, **_k: _Response(payload)
    )
    board = CareerBoard(firm="Jane Street", ats="greenhouse", token="janestreet")
    source = CareersSource(Settings(max_items_per_source=10), CareersSources(firms=[board]))

    items = list(source.fetch())

    assert len(items) == 1
    item = items[0]
    # Stable id (source, external_id) is the whole dedup guard — re-running must not change it.
    assert item.external_id == "careers:greenhouse:janestreet:12345"
    assert item.title == "[Jane Street] Quantitative Researcher — Systematic Equities"
    assert item.raw["firm"] == "Jane Street"
    assert "New York" in item.body  # location context is folded into the body
    # HTML fully unescaped and stripped — no lingering tags or entities.
    assert "<" not in item.body and "&lt;" not in item.body and "&amp;" not in item.body
    assert "Build alpha models with & deploy them." in item.body


def test_lever_jobs_parse_epoch_millis_and_categories(monkeypatch):
    payload = [
        {
            "id": "abc-uuid",
            "text": "Low-Latency C++ Engineer",
            "hostedUrl": "https://jobs.lever.co/firm/abc-uuid",
            "createdAt": 1_700_000_000_000,  # epoch millis
            "categories": {"team": "Core Trading", "location": "Chicago"},
            "descriptionPlain": "Write fast matching-engine code.",
        }
    ]
    monkeypatch.setattr(
        "alpha_engine.ingestion.careers.httpx.get", lambda *_a, **_k: _Response(payload)
    )
    board = CareerBoard(firm="Some HFT", ats="lever", token="firm")
    source = CareersSource(Settings(max_items_per_source=10), CareersSources(firms=[board]))

    items = list(source.fetch())

    assert len(items) == 1
    assert items[0].external_id == "careers:lever:firm:abc-uuid"
    assert items[0].created_at is not None and items[0].created_at.year == 2023
    assert "Core Trading" in items[0].body


def test_unknown_ats_is_skipped_not_fatal(monkeypatch):
    # A misconfigured ATS must log-and-skip, never crash the run.
    monkeypatch.setattr(
        "alpha_engine.ingestion.careers.httpx.get",
        lambda *_a, **_k: (_ for _ in ()).throw(AssertionError("should not be called")),
    )
    board = CareerBoard(firm="Mystery", ats="workday", token="x")
    source = CareersSource(Settings(), CareersSources(firms=[board]))

    assert list(source.fetch()) == []


def test_careers_is_alpha_stream_and_registry_gates_on_enable():
    assert stream_for("careers") == "alpha"

    board = CareerBoard(firm="Jane Street", ats="greenhouse", token="janestreet")
    # Disabled -> not built even with firms configured.
    disabled = Sources(careers=CareersSources(enabled=False, firms=[board]))
    assert build_sources(Settings(), disabled, only=["careers"]) == []
    # Enabled with firms -> built.
    enabled = Sources(careers=CareersSources(enabled=True, firms=[board]))
    built = build_sources(Settings(), enabled, only=["careers"])
    assert [s.source for s in built] == ["careers"]
