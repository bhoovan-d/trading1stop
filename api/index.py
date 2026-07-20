"""Vercel Python serverless entrypoint — the read-only JSON API.

Vercel's @vercel/python runtime serves the module-level ASGI ``app`` directly. This is a slim
app: it exposes the same ``/api/*`` router the local server uses, but does NOT mount the built SPA
(Vercel serves ``frontend/dist`` statically) and does NOT run schema migrations (the daily GitHub
Actions pipeline owns the schema via ``alpha-engine init-db``). Keeping generation/ingestion out of
the import path is what lets this function stay small — see requirements.txt.

Routing: vercel.json rewrites ``/api/(.*)`` here; FastAPI keeps its own ``/api`` prefix and matches
the original request path.
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

from alpha_engine.api.routes import router  # noqa: E402

app = FastAPI(title="Trading Alpha Engine API", version="0.1.0")


@app.middleware("http")
async def fix_vercel_rewrites(request: Request, call_next):
    # Vercel rewrites /api/(.*) to /api/index.
    # Restore original path from Vercel headers if present.
    matched = (
        request.headers.get("x-matched-path")
        or request.headers.get("x-forwarded-uri")
        or request.headers.get("x-original-url")
    )
    if matched and matched != request.url.path:
        request.scope["path"] = matched.split("?")[0]
    elif request.url.path in ("/api", "/api/", "/api/index"):
        request.scope["path"] = "/api/health"
    return await call_next(request)


# Same-origin in production (Vercel serves the SPA and this API on one domain), so CORS is only
# needed for local cross-origin dev against a deployed API. Harmless to keep permissive on GET.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["GET"],
    allow_headers=["*"],
)


@app.get("/api/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/api")
@app.get("/api/")
@app.get("/api/index")
def api_root() -> dict[str, str]:
    return {"status": "ok"}


app.include_router(router)

