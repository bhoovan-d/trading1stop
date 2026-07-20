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

class ClearRootPathMiddleware:
    """Vercel's ASGI adapter sometimes sets root_path, which breaks FastAPI's IncludedRouter matching."""
    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] == "http":
            scope["root_path"] = ""
        await self.app(scope, receive, send)

app.add_middleware(ClearRootPathMiddleware)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["GET"],
    allow_headers=["*"],
)

_include_router_error: str | None = None
if _router is not None:
    try:
        # Flatten routes directly into the app to avoid _IncludedRouter ASGI root_path issues on Vercel
        for route in _router.routes:
            app.router.routes.append(route)
    except Exception as _inc_exc:  # noqa: BLE001
        _include_router_error = repr(_inc_exc)


@app.get("/api/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/api/debug")
async def debug(request: Request) -> dict:
    """Diagnostic endpoint — shows path, headers, registered routes, and router contents."""
    app_routes = [{"type": type(r).__name__, "path": getattr(r, "path", "?")} for r in app.routes]
    router_routes = [{"type": type(r).__name__, "path": getattr(r, "path", "?")} for r in (_router.routes if _router else [])]
    return {
        "path": request.url.path,
        "import_error": _router_import_error,
        "include_router_error": _include_router_error,
        "router_is_none": _router is None,
        "app_routes": app_routes,
        "router_routes_count": len(router_routes),
        "router_routes": router_routes,
    }


