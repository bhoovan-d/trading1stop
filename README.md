# Trading Alpha Engine

An automated data pipeline and intelligence hub that tracks how **Applied AI, Agentic AI, and
Machine Learning** are being used to improve the trading process — backtesting, execution mechanics,
and risk management (dynamic stop-losses, regime detection, etc.).

Every 24 hours the engine ingests updates from the projects, communities, and builders that matter,
routes the raw stream through an LLM that separates engineering **Alpha** from noise, stores the
structured insights in a lightweight database, generates a ready-to-publish Markdown newsletter
draft, and serves everything through a filterable web dashboard.

```
 ingest ──▶ AI filter & synthesize ──▶ store (PostgreSQL) ──▶ newsletter draft
   │                                        │
   └─────────────── FastAPI JSON API ◀──────┘
                            │
                    React insight-feed SPA
```

---

## Chosen Stack (and why)

| Concern | Choice | Rationale |
| --- | --- | --- |
| Language | **Python 3.11+** | The entire quant / backtesting / AI-finance ecosystem we ingest (vectorbt, backtesting.py, FinRL, qlib, autogen, langgraph) is Python. One language for scraping, LLM orchestration, storage, and the API. |
| Packaging | **uv** (`pyproject.toml` + `uv.lock`) | Fast, reproducible, single lockfile. |
| GitHub ingestion | **PyGithub** | Commits + releases across many repos with sane rate-limit handling. |
| Reddit ingestion | **RSS by default** (no OAuth), **PRAW** optional | r/algotrading + r/quant come in credential-free via Reddit's public RSS feeds; PRAW is available as a richer opt-in path if you set up a Reddit app later. |
| RSS / blogs | **feedparser** | Robust feed parsing for "domain builders" and framework release feeds. |
| Forum scraping | **httpx + selectolax** | Fast HTML fetch/parse where no feed exists (QuantConnect, Freqtrade). RSS preferred where available. |
| Resilience | **tenacity** | Retries/backoff on flaky network sources. |
| LLM layer | **Free cascade** (Cerebras → Groq → Gemini) via one OpenAI-compatible adapter, Anthropic optional | Synthesis runs at **zero cost**: a cascade router tries each configured provider and falls through on rate-limit/failure. Filling in even one free key makes the whole site work; Claude is an optional paid fallback. |
| Structured extraction | **Pydantic** | One `InsightExtraction` contract every provider fulfills. |
| Storage | **PostgreSQL via SQLModel** | Durable source health, discovery history, and typed API data. |
| Scheduling | **APScheduler** + **Typer** CLI | Run once (cron-friendly) or run a built-in 24h daemon. |
| Config | **pydantic-settings** (`.env`) + `sources.yaml` | Secrets in env; targets editable without code changes. |
| Logging | **loguru** | Structured, readable logs. |
| Web API | **FastAPI + uvicorn** | Typed JSON API straight over the SQLModel session. |
| Frontend | **React + Vite + TypeScript**, Tailwind v4, TanStack Query, React Router | A fast, filterable **insight feed** dashboard. |

---

## Pipeline

1. **Ingest** — each source adapter yields `RawItem` drafts. Dedup is enforced by a unique
   `(source, external_id)` constraint, so nothing is ingested twice.
2. **AI filter & synthesize** — each new raw item is sent through the configured LLM provider, which
   returns a single structured object: a **relevance score (1–10)**, a **category tag**, a
   **2–3 sentence technical summary**, and a **trader-impact** note. Anything scoring **below 7** is
   discarded as noise.
3. **Store** — surviving insights and source-health records are persisted to PostgreSQL.
4. **Newsletter** — the day's insights (score-sorted, grouped by category) are rendered to
   `data/newsletters/YYYY-MM-DD.md`, a publish-ready draft.

### Insight categories

Primary axis — **trading style**:
`Technical Analysis` · `Macro Analysis` · `Intraday Trading` · `Swing Trading` · `Fundamental Analysis` · `Quant Firms`

Secondary axis — **tech approach** (sub-tags, 0–2 per item):
`Agentic AI` · `Machine Learning` · `Automation` · `Sentiment & News` · `Infrastructure & Data` · `Risk & Sizing`

---

## Tracked sources

Targets live in [`sources.yaml`](./sources.yaml) — edit that file to retarget, no code changes needed.

- **Core frameworks:** vectorbt, backtesting.py, QuantConnect/Lean, freqtrade, backtrader
- **AI / Agentic frameworks:** FinRL, FinGPT, FinRobot, qlib, RD-Agent, autogen, langgraph, crewAI
- **Infrastructure:** GitHub search for market-data **MCP servers**
- **Community:** Reddit, Bluesky public search, the QuantConnect forum, and optional StockTwits
  Firestream for provisioned accounts
- **Competitions:** Numerai public tournament snapshots, leaderboard signals, and forum updates
- **Research/blogs (RSS):** arXiv q-fin (TR/CP/RM/PM) + quant/AI builder blogs
- **Domain builders:** developer blogs / RSS feeds (extensible). Twitter/X is stubbed and ready to
  enable with credentials later.

### Two streams: alpha vs community

Insights carry a **stream**. The **alpha** stream (GitHub, research feeds, MCP) is the high-signal
engineering feed and the only content in the published newsletter; anything below the strict
relevance bar (`RELEVANCE_THRESHOLD`, default 7) is discarded. The **community** stream —
**r/algotrading, r/quant, r/quantconnect** (credential-free subreddit RSS) and the **QuantConnect
forum** (scraped newest-first) — is discussion, held to a lighter bar
(`COMMUNITY_RELEVANCE_THRESHOLD`, default 5) and shown in a separate **Community** tab in the UI.
(Freqtrade has no free community API — its Discussions are disabled and its community is Discord-only —
so freqtrade/crypto is covered via r/algotrading and its release feed.)

---

## Setup

### Backend

```bash
uv sync                       # install locked deps into .venv
cp .env.example .env          # then fill in your keys
set DATABASE_URL=postgresql://trading_alpha:change-me@localhost:5432/trading_alpha
uv run alpha-engine init-db   # apply versioned PostgreSQL schema migrations
```

### Move an existing SQLite feed

Keep the old SQLite file as a backup, point `DATABASE_URL` at an empty PostgreSQL database, then run:

```bash
uv run alpha-engine migrate-sqlite data/alpha.db
uv run alpha-engine source-health
```

All environment variables are documented in [`.env.example`](./.env.example) — everything is **free**:

| Variable | Where to get it (free) | Enables |
| --- | --- | --- |
| `CEREBRAS_API_KEY` | [cloud.cerebras.ai](https://cloud.cerebras.ai/) | LLM synthesis (fastest free tier) |
| `GROQ_API_KEY` | [console.groq.com/keys](https://console.groq.com/keys) | LLM synthesis (fallback) |
| `GEMINI_API_KEY` | [aistudio.google.com/apikey](https://aistudio.google.com/apikey) | LLM synthesis (fallback) |
| `GITHUB_TOKEN` | GitHub → Settings → Developer settings → Tokens | GitHub repos + MCP discovery at full rate limits |
| _(none needed)_ | — | r/algotrading + r/quant, already wired via Reddit's public RSS feeds |
| `REDDIT_CLIENT_ID` / `REDDIT_CLIENT_SECRET` (optional) | [reddit.com/prefs/apps](https://www.reddit.com/prefs/apps) (type: script) | Richer PRAW/OAuth Reddit path (vote counts, comments) — not required |

**Filling in even one LLM key makes the whole site work** — the synthesis cascade tries providers in
`LLM_PROVIDER_CHAIN` order and uses the first that answers, so extra keys are just rate-limit
fallbacks. RSS (including Reddit) and forums need no credentials. The pipeline degrades gracefully
when a source's
credentials are absent — it simply skips that source.

### Frontend

```bash
cd frontend
npm install
npm run dev          # http://127.0.0.1:5173; proxies /api to FastAPI on port 8000
```

### Local development

Run the API and frontend in separate terminals:

```bash
# terminal 1, from the repository root
uv run alpha-engine serve

# terminal 2
cd frontend
npm run dev
```

Open `http://127.0.0.1:5173`. The API health check is available at
`http://127.0.0.1:8000/api/health`.

### Built-site preview

Build the SPA, then let FastAPI serve it together with the API:

```bash
cd frontend
npm run build
cd ..
uv run alpha-engine serve
```

Open `http://127.0.0.1:8000`.

---

## Running

```bash
# one full pass: ingest -> synthesize -> store -> newsletter  (call this from cron)
uv run alpha-engine run-once

# just fetch, no LLM spend (great for a dedup smoke test)
uv run alpha-engine ingest-only --source github

# regenerate today's newsletter from stored insights
uv run alpha-engine gen-newsletter

# built-in scheduler: run the full pipeline every 24h
uv run alpha-engine schedule

# serve the JSON API (and the built SPA in production)
uv run alpha-engine serve --reload
```

Cron example (daily at 07:00):

```
0 7 * * *  cd /path/to/trading-alpha-engine && uv run alpha-engine run-once >> data/cron.log 2>&1
```

---

## Extending the LLM layer (free-LLM cascade)

Synthesis calls an `LLMProvider`; a `CascadeProvider` tries each configured provider in
`LLM_PROVIDER_CHAIN` order until one returns a valid insight. Cerebras, Groq, and Gemini all share a
single **OpenAI-compatible** adapter (`intelligence/openai_compat_provider.py`), and Claude has its
own adapter — all fulfilling the same `InsightExtraction` contract.

Adding another free OpenAI-compatible provider is two lines: register a factory in
`intelligence/provider.py` (`_FACTORIES`) with its base URL, and add its key to `.env` +
`LLM_PROVIDER_CHAIN`. **No pipeline code changes required.**

---

## Layout

```
src/alpha_engine/
  config.py            settings + sources.yaml loader
  models.py            SQLModel tables (RawItem, Insight) + Category enum
  db.py                engine / init_db / session
  ingestion/           source adapters (github, reddit, rss, forums, mcp, twitter[stub])
  intelligence/        provider framework, Claude adapter, prompts, synthesis
  storage/             repository (dedup + persistence)
  newsletter/          Markdown draft generator
  api/                 FastAPI app + routes + schemas
  orchestrate.py       run_pipeline()
  cli.py               Typer entrypoint
frontend/              React + Vite + TS insight-feed dashboard
api/index.py           Vercel serverless entrypoint (slim read-only API)
vercel.json            Vercel build + routing (SPA static + /api function)
.github/workflows/     daily.yml — the once-a-day pipeline on GitHub Actions
```

---

## Deployment (Vercel + Supabase + GitHub Actions)

The app splits into three pieces around one Supabase Postgres database:

| Piece | Runs on | What it does |
|---|---|---|
| SPA + read API | **Vercel** | Serves `frontend/dist` statically and the `/api/*` read endpoints via a slim Python serverless function (`api/index.py`). Read-only — never runs the LLM. |
| Daily pipeline | **GitHub Actions** (`.github/workflows/daily.yml`) | Once a day: `init-db` (migrations) → `run-once` (ingest → synthesize → newsletter), writing insights + the daily brief to Supabase. |
| Database | **Supabase** | Single source of truth (Postgres). |

Why the pipeline isn't on Vercel: a real run takes several minutes with rate-limited free LLM
tiers, well past Vercel's serverless time limit. GitHub Actions has no such limit.

**1. Supabase** — create the project (already done here). You'll use two connection strings
(Project Settings → Database → Connection string): the **Transaction pooler** URL (port 6543) for
Vercel's serverless function, and the **Session pooler** URL (port 5432) for GitHub Actions + local
migration (the direct URL is IPv6-only; Actions runners are IPv4). See `.env.example` for the formats.

**2. Vercel** — import the GitHub repo. `vercel.json` already sets the build (`npm run build` →
`frontend/dist`) and routes `/api/*` to the function. Set one env var:
- `DATABASE_URL` = the Supabase **pooler** URL (`...pooler.supabase.com:6543/postgres?sslmode=require`).
Deploy, then check `https://<app>/api/health` → `{"status":"ok"}` and `/api/meta`.

**3. GitHub Actions** — add repository **Secrets**: `DATABASE_URL` (the **Session pooler** 5432 URL), your
LLM keys (`CEREBRAS_API_KEY`, `GROQ_API_KEY`, `GEMINI_API_KEY`, `SAMBANOVA_API_KEY`, optional
`ANTHROPIC_API_KEY`), `GH_INGEST_TOKEN` (a PAT for GitHub ingestion), and `REDDIT_CLIENT_ID` /
`REDDIT_CLIENT_SECRET`. Trigger the workflow once via **Actions → Daily pipeline → Run workflow**
to populate the DB, then it runs daily at 06:00 UTC.

> If Supabase already has an older `insight` table without the `approaches` column, run once:
> `ALTER TABLE insight ADD COLUMN approaches TEXT NOT NULL DEFAULT '[]';`

---

## Notes & caveats

- **Site not loading locally?** Confirm the backend health endpoint returns `{"status":"ok"}` on
  port 8000, then start Vite on port 5173 for development. Vite proxies `/api` to port 8000;
  alternatively, build the frontend and open the FastAPI-served site directly on port 8000.

- **Forum scraping is best-effort.** Community forums change their markup; selectors are isolated in
  `ingestion/forums.py`. RSS is used wherever a feed exists.
- **Twitter/X is stubbed.** The adapter implements the source interface but stays disabled unless
  `TWITTER_ENABLED=true` and credentials are supplied.
- Generated data (`data/`) and secrets (`.env`) are git-ignored.
