# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this is

Trading Alpha Engine — an automated pipeline that ingests updates from AI/ML-in-trading projects
(GitHub repos, Reddit, forums, RSS/research feeds), routes them through an LLM that scores relevance
and writes structured insights, stores them in SQLite, generates a daily Markdown newsletter, and
serves everything through a FastAPI JSON API + React SPA. Python backend under `src/alpha_engine/`,
frontend under `frontend/`.

## Commands

Backend is managed with **uv**; frontend with **npm**. Run from the repo root.

```bash
# Backend setup / deps
uv sync                                   # install locked deps into .venv
uv sync --extra dev                       # include pytest (it is an OPTIONAL dep — see gotchas)

# Tests  ── plain `uv run pytest` FAILS ("program not found"); pytest lives in [dev]
uv run --extra dev pytest -q
uv run --extra dev pytest tests/test_pipeline.py::test_dedup -q   # single test

# Pipeline CLI (entrypoint `alpha-engine` = alpha_engine.cli:app)
uv run alpha-engine init-db
uv run alpha-engine ingest-only --source rss        # fetch only, no LLM; -s repeatable
uv run alpha-engine run-once                         # ingest → synthesize → store → newsletter
uv run alpha-engine gen-newsletter [--date YYYY-MM-DD]
uv run alpha-engine schedule [--hours 24] [--no-run-now]
uv run alpha-engine serve [--reload]                 # API on :8000 (+ built SPA in prod)
uv run alpha-engine seed-demo [--count 24]           # insert fake insights (no LLM) for UI/dev

# Frontend
cd frontend && npm install
npm run dev            # Vite on :5173, proxies /api → 127.0.0.1:8000
npm run build          # emits frontend/dist (what `serve` mounts in prod)
npm run typecheck      # tsc --noEmit (build itself does not typecheck)
```

Source targets (repos, subreddits, feeds) live in `sources.yaml` — editable with no code changes.
Secrets live in `.env` (copy from `.env.example`).

## Architecture (the parts that span files)

**Four-phase pipeline**, wired by `orchestrate.run_pipeline`: **ingest → synthesize → store →
newsletter**. Each phase is independently runnable via the CLI, and each degrades gracefully (a
source or provider that isn't configured is skipped, never fatal).

**Ingestion is pluggable.** Every adapter subclasses `ingestion/base.py::Source` and yields
`RawItemDraft`s from `fetch()`. `ingestion/registry.py::build_sources` maps source names
(`github`, `reddit`, `rss`, `forum`, `mcp`, `twitter`) to adapters and is the single place sources
are enabled. **Dedup is the core invariant**: `RawItem` has a unique `(source, external_id)`
constraint, and `storage/repository.py::save_raw` inserts only new pairs — so re-ingestion is a
no-op and every adapter just needs a *stable* `external_id`. Twitter is a deliberate disabled stub.

**The LLM layer is provider-agnostic and the main extension point.** `intelligence/provider.py`
defines the `LLMProvider` protocol (`extract(item) -> InsightExtraction | None`) and a
`CascadeProvider` that tries providers in `LLM_PROVIDER_CHAIN` order, falling through to the next on
any `None`/error (this is how free-tier rate limits are absorbed). `build_provider` **skips any
provider whose API key is unset**, so configuration is entirely env-driven. Two adapters exist:
`openai_compat_provider.py` (one OpenAI-compatible client serving Cerebras / Groq / Gemini — and any
future free provider) and `anthropic_provider.py` (Claude, optional paid fallback). All return the
same `InsightExtraction` Pydantic contract (`models.py`). **To add a provider**: register a factory
in `provider.py::_FACTORIES`, add its key/model/base_url to `config.py::Settings`, and list its name
in `LLM_PROVIDER_CHAIN`. No pipeline code changes.

**Synthesis** (`intelligence/synthesize.py`) is **concurrent** (a `ThreadPoolExecutor` of
`SYNTHESIS_WORKERS`); worker threads call `provider.extract` on *detached* `RawItem`s and the calling
thread persists results and commits **per item** (so a kill mid-run keeps everything already scored).
The `CascadeProvider` **rotates** its starting provider per call (`itertools.count`) so concurrent load
spreads across all keys instead of stampeding provider #1.

**Two streams + per-stream threshold.** `config.COMMUNITY_SOURCES = {"reddit","forum"}` and
`config.stream_for(source)` are the single source of truth. Community items are scored against
`COMMUNITY_RELEVANCE_THRESHOLD` (default 5); everything else against `RELEVANCE_THRESHOLD` (default 7).
Both kept and discarded items set `RawItem.processed = True`; a provider failure/refusal returns `None`
and the item is **left unprocessed on purpose** so the next run retries it. The API's `stream` filter
(`alpha`/`community`) and the newsletter (alpha-only) both derive from `COMMUNITY_SOURCES` — keep that
set authoritative.

**Storage** is SQLModel over SQLite (`db.py` engine + `session_scope`, `models.py` tables). The API
(`api/`) reads the same models: `routes.py` exposes `/api/insights` (category / min_score / source /
date / search / sort / pagination), `/api/meta` (drives the UI's filter controls), and
`/api/newsletters[/{date}]`. `api/app.py` mounts the built SPA (`frontend/dist`) at `/` in prod and
enables CORS for the Vite dev origin — so `serve` alone delivers both API and UI on one port.

**Newsletter** is rendered from the DB per-date (`newsletter/generate.py::markdown_for_date`), not
from files; `gen-newsletter` writes the `.md` artifact. The API newsletter view uses the same
renderer, so both stay in sync.

**Frontend** (`frontend/src/`): React + Vite + TS, TanStack Query for server state, React Router.
`routes/FeedPage.tsx` is the centerpiece; **all filter/pagination state lives in the URL query
string** (via `useSearchParams`), making views shareable and back-button-friendly. `types.ts` mirrors
the API DTOs; `api/client.ts` holds the query hooks. Design tokens are Tailwind v4 `@theme` variables
in `index.css` (warm off-white "First Light" palette — see DESIGN.md); `components/Markdown.tsx` is a
minimal renderer tuned to the newsletter format this app generates (not a general Markdown engine).

## Conventions & gotchas

- **Two classification axes.** `Category` is the PRIMARY axis — the **trading style** an item speaks
  to: `"Technical Analysis"`, `"Macro Analysis"`, `"Intraday Trading"`, `"Swing Trading"`,
  `"Fundamental Analysis"`, `"Quant Firms"`. `Approach` is the SECONDARY axis — the **tech** used:
  `"Agentic AI"`, `"Machine Learning"`, `"Automation"`, `"Sentiment & News"`, `"Infrastructure & Data"`,
  `"Risk & Sizing"` (0-2 per item, rendered as sub-tags). Both are human-readable strings stored
  verbatim (`Insight.category`; `Insight.approaches` is a JSON array), reused as the LLM's
  structured-output enums, and normalized case-insensitively by the OpenAI-compat provider. The whole
  brief is pitched at **retail/independent algo-traders** — the prompt de-scores PhD-level academic
  content in favor of what a self-directed trader can actually use.
- **Re-classifying history**: `alpha-engine reclassify` wipes insights + briefs (recreating those
  tables so schema changes like `approaches` apply), resets every `RawItem.processed = False`, and
  re-runs synthesis over the preserved raw content — no re-ingestion.
- **pytest is an optional dep** in `pyproject.toml [dev]`; `uv sync` prunes it. Always test with
  `uv run --extra dev pytest`.
- **Windows file-lock**: a running `alpha-engine serve` locks `.venv/Scripts/alpha-engine.exe`, so
  `uv sync` fails with "process cannot access the file". Stop the server first — the reliable kill is
  by port: PowerShell `Get-NetTCPConnection -LocalPort 8000 -State Listen | ... Stop-Process`
  (`pkill -f` does not match Windows processes under Git Bash).
- **Config caching**: `get_settings()` / `get_sources()` are `lru_cache`d. Tests that need a fresh DB
  set env `DB_PATH`, then call `config.get_settings.cache_clear()` and reset `db._engine = None`
  before `init_db()` (see `tests/test_pipeline.py::temp_db`).
- `sources.yaml` empty keys (`handles:` with only comments → `None`) are pruned by
  `config._prune_none` so model defaults apply — keep that when adding config sections.
- After changing frontend code, `npm run build` before relying on `serve` (prod serves `dist`); in
  dev, run Vite (5173) and `serve` (8000) together and use the proxy.
- Ingesting many GitHub repos on a first `run-once` produces a large batch; free LLM tiers pace it and
  unprocessed items retry next run, so it self-throttles rather than failing.

## Deployment (Vercel + Supabase + GitHub Actions)

Three pieces around one Supabase Postgres DB (`DATABASE_URL`). See README "Deployment" for the full guide.
- **Vercel** serves the SPA (`frontend/dist`, static) + the **read-only** API via `api/index.py` — a
  *slim* FastAPI app (router only; no SPA mount, no `init_db`). It must stay import-light: it deliberately
  does **not** import the LLM/ingestion layer, so `requirements.txt` (root) lists only read deps. If you
  add a read endpoint that imports `intelligence`/`ingestion` at module scope, you'll bloat the function —
  keep such imports lazy (as `newsletter/generate.py` does with `build_provider`/`generate_editorial`).
  `vercel.json` builds the frontend and rewrites `/api/*` → the function; `db.py` uses `NullPool` when
  `VERCEL` is set (Supabase transaction pooler).
- **GitHub Actions** (`.github/workflows/daily.yml`) runs the pipeline once a day (`init-db` → `run-once`)
  against Supabase — the pipeline is too long/rate-limited for a Vercel function. `api/app.py` (SPA-mount +
  `init_db`) remains the **local/Docker** entrypoint; Vercel uses `api/index.py`.

## Design Context

Two root files capture the product's strategy and visual system; read them before UI work.

- **[PRODUCT.md](PRODUCT.md)** — the strategic "who/why". Register: **product**; platform: **web**.
  Audience is independent & retail algo-traders; it ships as a public product + newsletter whose
  positioning is *scored signal, noise filtered out*. Personality is **calm, editorial, curated**;
  the anti-reference is generic AI-generated SaaS. Principles: signal over volume · curated, not
  comprehensive · approachable expertise · earn trust through transparency · a calm daily ritual.
  Accessibility target is **WCAG 2.1 AA**.
- **[DESIGN.md](DESIGN.md)** — the visual system, "First Light": a warm off-white surface, pure-white
  cards on soft warm shadows, one poppy-coral accent used sparingly, Fraunces serif for display +
  reading with Inter for UI, and tabular mono for data. Tokens are the `@theme` block in
  `frontend/src/index.css`; `.impeccable/design.json` is the machine-readable sidecar. Light-only by
  design. Do **not** drift back toward a saturated cream background or the old dark terminal.
