"""Admin API: pipeline status + on-demand runs, behind a shared-secret token.

The pipeline takes minutes and needs the LLM/ingestion libraries the Vercel function deliberately
excludes (see the root requirements.txt), and vercel.json caps the function at 30s. So nothing here
runs the pipeline — ``POST /api/admin/run`` dispatches the GitHub Actions workflow that already does,
and ``GET /api/admin/runs`` reports back on it.

Two rules this module must keep:
  * No module-scope import of ``intelligence`` or ``ingestion`` — that is what keeps the serverless
    function small (``newsletter/generate.py`` lazy-imports for the same reason).
  * HTTP via stdlib ``urllib.request``, not httpx/requests — adding a dependency to the slim
    requirements.txt would defeat the point.
"""

from __future__ import annotations

import hmac
import json
import re
import urllib.error
import urllib.request
from collections.abc import Iterator
from datetime import datetime

from fastapi import APIRouter, Depends, Header, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import func
from sqlmodel import Session, select

from ..config import get_settings
from ..db import get_engine
from ..models import DailyBrief, Insight, RawItem, SourceRegistry

router = APIRouter(prefix="/api/admin", tags=["admin"])

# Must match the `mode` choices in .github/workflows/daily.yml. Validated server-side so a client
# can never dispatch a mode the workflow does not understand.
RUN_MODES = ("full", "ingest", "synthesize", "rescore", "newsletter", "reclassify")

_GITHUB_API = "https://api.github.com"
_TIMEOUT = 15


def get_session() -> Iterator[Session]:
    with Session(get_engine()) as session:
        yield session


def require_admin(x_admin_token: str = Header(default="")) -> None:
    """Gate every admin endpoint on a shared secret.

    Fails closed: with ADMIN_TOKEN unset, nothing is reachable, so a half-configured deploy is
    never an open door. compare_digest keeps the check constant-time.
    """
    expected = get_settings().admin_token
    if not expected:
        raise HTTPException(status_code=503, detail="Admin API is not configured (ADMIN_TOKEN unset).")
    if not hmac.compare_digest(x_admin_token or "", expected):
        raise HTTPException(status_code=401, detail="Unauthorized")


# ---- schemas ------------------------------------------------------------------


class AdminStatusOut(BaseModel):
    total_insights: int
    latest_insight_at: datetime | None = None
    total_raw_items: int
    unprocessed_raw_items: int
    latest_newsletter: str | None = None
    source_count: int = 0
    dispatch_configured: bool = False


class RunRequest(BaseModel):
    mode: str = Field(default="full")
    sources: str = ""


class RunOut(BaseModel):
    id: int
    name: str | None = None
    status: str | None = None
    conclusion: str | None = None
    created_at: str | None = None
    html_url: str | None = None
    display_title: str | None = None


# ---- GitHub dispatch ----------------------------------------------------------


def _github(path: str, *, method: str = "GET", payload: dict | None = None) -> tuple[int, dict | list | None]:
    """Call the GitHub REST API with the configured PAT. Returns (status, parsed body|None)."""
    settings = get_settings()
    if not settings.github_repo or not settings.github_dispatch_token:
        raise HTTPException(
            status_code=503,
            detail="Workflow dispatch is not configured (set GITHUB_REPO and GITHUB_DISPATCH_TOKEN).",
        )

    request = urllib.request.Request(
        f"{_GITHUB_API}/repos/{settings.github_repo}{path}",
        method=method,
        data=json.dumps(payload).encode() if payload is not None else None,
        headers={
            "Accept": "application/vnd.github+json",
            "Authorization": f"Bearer {settings.github_dispatch_token}",
            "X-GitHub-Api-Version": "2022-11-28",
            "Content-Type": "application/json",
            "User-Agent": "trading-alpha-engine-admin",
        },
    )
    try:
        with urllib.request.urlopen(request, timeout=_TIMEOUT) as response:
            body = response.read()
            return response.status, (json.loads(body) if body else None)
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode(errors="replace")[:400]
        # Surface GitHub's own reason (bad PAT, missing workflow, wrong ref) — debugging a silent
        # 500 here is miserable. Never echo the token itself.
        raise HTTPException(status_code=502, detail=f"GitHub API {exc.code}: {detail}") from exc
    except urllib.error.URLError as exc:
        raise HTTPException(status_code=502, detail=f"Could not reach GitHub: {exc.reason}") from exc


# ---- endpoints ----------------------------------------------------------------


@router.get("/status", response_model=AdminStatusOut, dependencies=[Depends(require_admin)])
def admin_status(session: Session = Depends(get_session)) -> AdminStatusOut:
    """Pipeline health. Doubles as the token-validation call the UI uses to unlock."""
    settings = get_settings()
    latest_brief = session.exec(
        select(DailyBrief.brief_date).order_by(DailyBrief.brief_date.desc()).limit(1)
    ).first()

    return AdminStatusOut(
        total_insights=session.exec(select(func.count()).select_from(Insight)).one(),
        latest_insight_at=session.exec(
            select(func.max(Insight.created_at)).select_from(Insight)
        ).one(),
        total_raw_items=session.exec(select(func.count()).select_from(RawItem)).one(),
        # The number that says "a run is due": items ingested but not yet scored.
        unprocessed_raw_items=session.exec(
            select(func.count()).select_from(RawItem).where(RawItem.processed == False)  # noqa: E712
        ).one(),
        latest_newsletter=latest_brief,
        # Deliberately a plain COUNT, not repository.source_health(): that runs a COUNT per
        # registry row, and the N+1 was slow enough over the network to risk the function's 30s
        # limit. This endpoint only needs the number.
        source_count=session.exec(select(func.count()).select_from(SourceRegistry)).one(),
        dispatch_configured=bool(settings.github_repo and settings.github_dispatch_token),
    )


@router.post("/run", status_code=202, dependencies=[Depends(require_admin)])
def admin_run(body: RunRequest) -> dict:
    """Dispatch the pipeline workflow. Returns as soon as GitHub accepts it (202, empty body)."""
    settings = get_settings()
    mode = (body.mode or "full").strip()
    if mode not in RUN_MODES:
        raise HTTPException(status_code=400, detail=f"mode must be one of {', '.join(RUN_MODES)}")

    # `sources` only means anything to the phases that ingest.
    sources = body.sources.strip() if mode in ("full", "ingest") else ""
    if sources:
        # Defence in depth: this string is forwarded to a shell script on the Actions runner
        # (via an env var, not interpolation — but keep the value boring regardless). Adapter
        # names are plain identifiers, so anything else is rejected rather than escaped.
        names = [s.strip() for s in sources.split(",") if s.strip()]
        if not all(re.fullmatch(r"[a-z0-9_-]{1,32}", n) for n in names):
            raise HTTPException(status_code=400, detail="sources must be comma-separated adapter names")
        sources = ",".join(names)

    _github(
        f"/actions/workflows/{settings.github_workflow_file}/dispatches",
        method="POST",
        payload={
            "ref": settings.github_workflow_ref,
            "inputs": {"mode": mode, "sources": sources},
        },
    )
    return {"dispatched": True, "mode": mode, "sources": sources}


@router.get("/runs", response_model=list[RunOut], dependencies=[Depends(require_admin)])
def admin_runs() -> list[RunOut]:
    settings = get_settings()
    _, body = _github(f"/actions/workflows/{settings.github_workflow_file}/runs?per_page=10")
    runs = (body or {}).get("workflow_runs", []) if isinstance(body, dict) else []
    return [
        RunOut(
            id=run["id"],
            name=run.get("name"),
            status=run.get("status"),
            conclusion=run.get("conclusion"),
            created_at=run.get("created_at"),
            html_url=run.get("html_url"),
            display_title=run.get("display_title"),
        )
        for run in runs
    ]
