"""Vercel Python serverless entrypoint — the read-only JSON API.

Vercel's @vercel/python runtime serves the module-level ASGI ``app`` directly. This is a slim
app: it exposes the same ``/api/*`` router the local server uses, but does NOT mount the built SPA
(Vercel serves ``frontend/dist`` statically) and does NOT run schema migrations (the daily GitHub
Actions pipeline owns the schema via ``alpha-engine init-db``). Keeping generation/ingestion out of
the import path is what lets this function stay small — see requirements.txt.

Routing: vercel.json rewrites ``/api/(.*)`` here; Vercel preserves the original request path (e.g.
/api/insights, /api/meta) in the ASGI scope — FastAPI routes against those paths directly.
No path-mangling middleware is needed.
"""

from __future__ import annotations

import sys
from pathlib import Path

# The package lives under src/ (src layout); make it importable without a full project install.
_SRC = Path(__file__).resolve().parent.parent / "src"
if str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))

from fastapi import FastAPI, Request  # noqa: E402
from fastapi.middleware.cors import CORSMiddleware  # noqa: E402

_router_import_error: str | None = None
try:
    from alpha_engine.api.routes import router as _router  # noqa: E402
except Exception as _exc:  # noqa: BLE001
    _router_import_error = repr(_exc)
    _router = None  # type: ignore[assignment]

app = FastAPI(title="Trading Alpha Engine API", version="0.1.0")

# Same-origin in production (Vercel serves the SPA and this API on one domain), so CORS is only
# needed for local cross-origin dev against a deployed API. Harmless to keep permissive on GET.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["GET"],
    allow_headers=["*"],
)

if _router is not None:
    app.include_router(_router)


@app.get("/api/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/api/debug")
async def debug(request: Request) -> dict:
    """Diagnostic endpoint — shows path, headers, and all registered routes."""
    registered = []
    for route in app.routes:
        if hasattr(route, "path"):
            registered.append(route.path)
    return {
        "path": request.url.path,
        "scope_path": request.scope.get("path"),
        "registered_routes": registered,
        "import_error": _router_import_error,
        "headers": {k: v for k, v in request.headers.items()},
    }


