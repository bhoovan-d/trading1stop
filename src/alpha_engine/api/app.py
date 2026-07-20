"""FastAPI application: JSON API + (in production) the built SPA."""

from __future__ import annotations

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from ..config import ROOT_DIR, get_settings
from ..db import init_db
from .routes import router

settings = get_settings()

app = FastAPI(title="Trading Alpha Engine API", version="0.1.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        settings.frontend_origin,
        "http://localhost:5173",
        "http://127.0.0.1:5173",
    ],
    allow_methods=["*"],
    allow_headers=["*"],
)

# Tables exist even when the API is launched directly (e.g. uvicorn --reload subprocess).
init_db()


@app.get("/api/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


app.include_router(router)

# Serve the built SPA in production (frontend/dist). During dev the Vite server proxies /api.
_DIST = ROOT_DIR / "frontend" / "dist"
if _DIST.exists():
    _assets = _DIST / "assets"
    if _assets.exists():
        app.mount("/assets", StaticFiles(directory=_assets), name="assets")

    @app.get("/{full_path:path}", include_in_schema=False)
    def spa(full_path: str) -> FileResponse:
        candidate = _DIST / full_path
        if full_path and candidate.is_file():
            return FileResponse(candidate)
        return FileResponse(_DIST / "index.html")  # client-side routing fallback
