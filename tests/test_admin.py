"""Admin API tests: the token gate, and dispatch without touching GitHub."""

from __future__ import annotations

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from alpha_engine import config, db
from alpha_engine.api import admin

TOKEN = "test-admin-token-value"


@pytest.fixture()
def client(tmp_path, monkeypatch):
    """App with only the admin router mounted, against a throwaway SQLite DB."""
    monkeypatch.setenv("DB_PATH", str(tmp_path / "admin.db"))
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{tmp_path / 'admin.db'}")
    monkeypatch.setenv("ADMIN_TOKEN", TOKEN)
    monkeypatch.setenv("GITHUB_REPO", "owner/repo")
    monkeypatch.setenv("GITHUB_DISPATCH_TOKEN", "ghp_fake")
    config.get_settings.cache_clear()
    config.get_sources.cache_clear()
    db._engine = None
    db.init_db()

    app = FastAPI()
    app.include_router(admin.router)
    yield TestClient(app)

    db._engine = None
    config.get_settings.cache_clear()


def test_status_requires_a_token(client):
    assert client.get("/api/admin/status").status_code == 401
    assert client.get("/api/admin/status", headers={"X-Admin-Token": "wrong"}).status_code == 401


def test_status_returns_counts_with_a_valid_token(client):
    response = client.get("/api/admin/status", headers={"X-Admin-Token": TOKEN})
    assert response.status_code == 200
    body = response.json()
    assert body["total_insights"] == 0
    assert body["unprocessed_raw_items"] == 0
    assert body["dispatch_configured"] is True


def test_admin_fails_closed_when_token_is_unset(client, monkeypatch):
    """A half-configured deploy must refuse, never fall open."""
    monkeypatch.delenv("ADMIN_TOKEN", raising=False)
    config.get_settings.cache_clear()
    assert client.get("/api/admin/status").status_code == 503
    assert client.get("/api/admin/status", headers={"X-Admin-Token": TOKEN}).status_code == 503


def test_run_rejects_an_unknown_mode(client):
    response = client.post(
        "/api/admin/run", json={"mode": "rm -rf"}, headers={"X-Admin-Token": TOKEN}
    )
    assert response.status_code == 400


def test_run_dispatches_the_workflow_with_mode_and_sources(client, monkeypatch):
    calls = []

    def fake_github(path, *, method="GET", payload=None):
        calls.append((path, method, payload))
        return 204, None

    monkeypatch.setattr(admin, "_github", fake_github)
    response = client.post(
        "/api/admin/run",
        json={"mode": "ingest", "sources": "github,reddit"},
        headers={"X-Admin-Token": TOKEN},
    )
    assert response.status_code == 202
    path, method, payload = calls[0]
    assert path == "/actions/workflows/daily.yml/dispatches"
    assert method == "POST"
    assert payload == {"ref": "main", "inputs": {"mode": "ingest", "sources": "github,reddit"}}


def test_run_drops_sources_for_phases_that_do_not_ingest(client, monkeypatch):
    """`sources` is meaningless to synthesize/newsletter/reclassify — don't pass it through."""
    calls = []
    monkeypatch.setattr(admin, "_github", lambda path, *, method="GET", payload=None: (
        calls.append(payload), (204, None))[1])
    client.post(
        "/api/admin/run",
        json={"mode": "synthesize", "sources": "github"},
        headers={"X-Admin-Token": TOKEN},
    )
    assert calls[0]["inputs"]["sources"] == ""


@pytest.mark.parametrize(
    "sources",
    ["github; rm -rf /", "github,$(whoami)", "github reddit", "`id`", "a" * 40, "git!hub"],
)
def test_run_rejects_shell_metacharacters_in_sources(client, monkeypatch, sources):
    """`sources` reaches a shell script on the Actions runner; keep the value boring."""
    monkeypatch.setattr(admin, "_github", lambda *a, **k: (204, None))
    response = client.post(
        "/api/admin/run",
        json={"mode": "ingest", "sources": sources},
        headers={"X-Admin-Token": TOKEN},
    )
    assert response.status_code == 400


def test_run_normalizes_valid_source_lists(client, monkeypatch):
    calls = []
    monkeypatch.setattr(admin, "_github", lambda path, *, method="GET", payload=None: (
        calls.append(payload), (204, None))[1])
    client.post(
        "/api/admin/run",
        json={"mode": "ingest", "sources": " github , reddit "},
        headers={"X-Admin-Token": TOKEN},
    )
    assert calls[0]["inputs"]["sources"] == "github,reddit"


def test_workflow_reads_inputs_from_env_not_interpolation():
    """Interpolating ${{ inputs.sources }} into the run script would be a shell-injection path."""
    from pathlib import Path

    workflow = Path(__file__).resolve().parents[1] / ".github" / "workflows" / "daily.yml"
    text = workflow.read_text(encoding="utf-8")
    assert "RUN_SOURCES: ${{ inputs.sources }}" in text
    assert 'sources="${{ inputs.sources }}"' not in text
    assert 'mode="${{ inputs.mode }}"' not in text


def test_run_modes_match_the_workflow_choices():
    """The API and .github/workflows/daily.yml must agree, or a dispatch 422s at GitHub."""
    import re
    from pathlib import Path

    workflow = Path(__file__).resolve().parents[1] / ".github" / "workflows" / "daily.yml"
    block = re.search(r"options:\n((?:\s+-\s+\w+\n)+)", workflow.read_text(encoding="utf-8"))
    assert block, "could not find the mode options block in daily.yml"
    assert set(re.findall(r"-\s+(\w+)", block.group(1))) == set(admin.RUN_MODES)


def test_workflow_has_no_schedule_trigger():
    """The daily schedule is what the user asked us to stop; keep it stopped."""
    from pathlib import Path

    import yaml

    workflow = Path(__file__).resolve().parents[1] / ".github" / "workflows" / "daily.yml"
    spec = yaml.safe_load(workflow.read_text(encoding="utf-8"))
    # PyYAML parses the bare `on:` key as the boolean True (YAML 1.1) — hence the fallback.
    triggers = spec.get("on", spec.get(True))
    assert "workflow_dispatch" in triggers
    assert "schedule" not in triggers
