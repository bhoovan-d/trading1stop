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

from fastapi import Depends, FastAPI, HTTPException, Request  # noqa: E402
from fastapi.middleware.cors import CORSMiddleware  # noqa: E402

_router_import_error: str | None = None
try:
    from alpha_engine.api.routes import router as _router  # noqa: E402
except Exception as _exc:  # noqa: BLE001
    _router_import_error = repr(_exc)
    _router = None  # type: ignore[assignment]

# Admin router is optional: if it fails to import, the read API must still serve.
_admin_import_error: str | None = None
try:
    from alpha_engine.api.admin import require_admin  # noqa: E402
    from alpha_engine.api.admin import router as _admin_router  # noqa: E402
except Exception as _adm_exc:  # noqa: BLE001
    _admin_import_error = repr(_adm_exc)
    _admin_router = None  # type: ignore[assignment]
    require_admin = None  # type: ignore[assignment]

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
    # POST is for /api/admin/run only; every admin route is gated by require_admin.
    allow_methods=["GET", "POST"],
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

# Same flattening for the admin routes, and registered here so they land BEFORE the
# /{full_path:path} SPA catch-all defined at the bottom of this file.
if _admin_router is not None:
    try:
        for route in _admin_router.routes:
            app.router.routes.append(route)
    except Exception as _adm_inc_exc:  # noqa: BLE001
        _admin_import_error = repr(_adm_inc_exc)

from fastapi.responses import HTMLResponse, FileResponse
import os

@app.get("/")
def serve_frontend_root():
    """Fallback: serve React index.html if Vercel routing sends / to FastAPI."""
    if os.path.exists("index.html"):
        with open("index.html", "r", encoding="utf-8") as f:
            return HTMLResponse(f.read())
    return {"detail": "Frontend index.html not found in lambda deployment"}

@app.get("/assets/{filename:path}")
def serve_frontend_assets(filename: str):
    """Fallback: serve React assets if Vercel routing sends /assets to FastAPI."""
    path = f"assets/{filename}"
    if os.path.exists(path):
        return FileResponse(path)
    return {"detail": "Asset not found"}

@app.get("/api/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/api/debug", dependencies=[Depends(require_admin)] if require_admin else [])
async def debug(request: Request) -> dict:
    """Diagnostic endpoint — shows path, headers, registered routes, and router contents.

    Admin-gated: it exposes the full route table and import errors, which is reconnaissance, not
    something to serve publicly. If the admin module failed to import there is no gate available,
    so it refuses outright rather than falling open.
    """
    if require_admin is None:
        raise HTTPException(status_code=503, detail="Admin module unavailable")
    app_routes = [{"type": type(r).__name__, "path": getattr(r, "path", "?")} for r in app.routes]
    router_routes = [{"type": type(r).__name__, "path": getattr(r, "path", "?")} for r in (_router.routes if _router else [])]
    return {
        "path": request.url.path,
        "import_error": _router_import_error,
        "include_router_error": _include_router_error,
        "admin_import_error": _admin_import_error,
        "router_is_none": _router is None,
        "app_routes": app_routes,
        "router_routes_count": len(router_routes),
        "router_routes": router_routes,
    }


# Backstop SPA fallback: if Vercel routes a client-side path (/launches, /jobs, /india, …) to the
# function instead of the static index.html, serve index.html so React Router can handle it. Kept
# LAST so it never shadows the /api/* and /assets/* routes registered above.
@app.get("/{full_path:path}")
def serve_spa(full_path: str):
    if full_path.startswith("api/") or full_path.startswith("assets/"):
        raise HTTPException(status_code=404, detail="Not Found")
    if os.path.exists("index.html"):
        with open("index.html", "r", encoding="utf-8") as f:
            return HTMLResponse(f.read())
    raise HTTPException(status_code=404, detail="Frontend index.html not found in lambda deployment")


