"""Configuration: environment settings + the editable sources.yaml target list."""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Any

import yaml
from pydantic import BaseModel, Field
from pydantic_settings import BaseSettings, SettingsConfigDict

# Project root = two levels up from this file (src/alpha_engine/config.py -> repo root).
ROOT_DIR = Path(__file__).resolve().parents[2]

# Sources whose content is community discussion rather than shipped engineering. Single
# source of truth used by synthesis (lower threshold) and the API (stream classification).
COMMUNITY_SOURCES = frozenset({"reddit", "forum", "bluesky", "stocktwits"})


def stream_for(source: str) -> str:
    """Classify a RawItem/Insight source into the 'community' or 'alpha' stream."""
    return "community" if source in COMMUNITY_SOURCES else "alpha"


class Settings(BaseSettings):
    """Environment-driven settings (loaded from .env, overridable by real env vars)."""

    model_config = SettingsConfigDict(
        env_file=ROOT_DIR / ".env",
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
    )

    # LLM / synthesis
    # Cascade order: free providers first, Anthropic last. build_provider() skips any
    # provider whose key is unset, so only what you configure in .env actually runs.
    llm_provider_chain: str = "cerebras,groq,gemini,anthropic"
    relevance_threshold: int = 7
    # Community sources (reddit/forums) are discussion, not shipped engineering, so they're
    # held to a lower bar than the alpha stream (GitHub / research / MCP).
    community_relevance_threshold: int = 5
    # Concurrent synthesis workers. Higher = faster on the first big backlog, but more
    # simultaneous load per provider. The cascade rotates providers so load spreads across
    # all configured keys; add more free providers to raise the ceiling before rate limits.
    synthesis_workers: int = 6
    # Bounded daily processing + a rolling "best of" site. The pipeline scores at most
    # synthesis_max_per_run freshest items per run (never hundreds), then prunes the stored
    # insights down to the top site_insight_target (alpha) / community_insight_target (community)
    # by score+recency — so the webpage always shows ~the best, not an ever-growing pile.
    synthesis_max_per_run: int = 60
    site_insight_target: int = 40
    community_insight_target: int = 20
    # Guaranteed minimums so the specialized tabs never go empty when their items don't crack
    # the overall top-N on score alone (jobs/India typically score below launches/tooling).
    # These are kept IN ADDITION to the top-N best, so the site stays small (~40 + these).
    retain_hiring: int = 6      # /jobs
    retain_india: int = 6       # /india
    retain_launches: int = 6    # /launches (launch + funding)

    # Anthropic (reference; optional)
    anthropic_api_key: str | None = None
    anthropic_model: str = "claude-opus-4-8"

    # Free OpenAI-compatible providers
    cerebras_api_key: str | None = None
    cerebras_model: str = "gpt-oss-120b"
    cerebras_base_url: str = "https://api.cerebras.ai/v1"

    groq_api_key: str | None = None
    groq_model: str = "llama-3.3-70b-versatile"
    groq_base_url: str = "https://api.groq.com/openai/v1"

    gemini_api_key: str | None = None
    gemini_model: str = "gemini-flash-lite-latest"
    gemini_base_url: str = "https://generativelanguage.googleapis.com/v1beta/openai/"

    sambanova_api_key: str | None = None
    sambanova_model: str = "gpt-oss-120b"  # strict JSON validator; gpt-oss is reliable, Llama-3.3 isn't
    sambanova_base_url: str = "https://api.sambanova.ai/v1"

    openrouter_api_key: str | None = None
    openrouter_model: str = "meta-llama/llama-3.3-70b-instruct:free"
    openrouter_base_url: str = "https://openrouter.ai/api/v1"

    # GitHub
    github_token: str | None = None

    # Reddit
    reddit_client_id: str | None = None
    reddit_client_secret: str | None = None
    reddit_user_agent: str = "trading-alpha-engine/0.1"

    # Twitter / X (stubbed)
    twitter_enabled: bool = False
    twitter_bearer_token: str | None = None

    # StockTwits Firestream (optional; access is provisioned by StockTwits)
    stocktwits_enabled: bool = False
    stocktwits_username: str | None = None
    stocktwits_password: str | None = None

    # Tunables
    database_url: str | None = None
    db_path: str = "data/alpha.db"
    max_items_per_source: int = 15
    newsletter_dir: str = "data/newsletters"
    frontend_origin: str = "http://localhost:5173"

    sources_file: str = "sources.yaml"

    # ---- derived helpers ------------------------------------------------------

    @property
    def provider_chain(self) -> list[str]:
        return [p.strip() for p in self.llm_provider_chain.split(",") if p.strip()]

    def resolve(self, relative: str) -> Path:
        """Resolve a config path against the project root (absolute paths pass through)."""
        p = Path(relative)
        return p if p.is_absolute() else ROOT_DIR / p

    @property
    def db_file(self) -> Path:
        return self.resolve(self.db_path)

    @property
    def newsletter_path(self) -> Path:
        return self.resolve(self.newsletter_dir)


# ---- sources.yaml models ------------------------------------------------------


class GithubSources(BaseModel):
    track: list[str] = Field(default_factory=lambda: ["commits", "releases"])
    repos: list[str] = Field(default_factory=list)


class RedditSources(BaseModel):
    subreddits: list[str] = Field(default_factory=list)
    listing: str = "top"
    time_filter: str = "week"
    min_score: int = 0


class RssFeed(BaseModel):
    name: str
    url: str
    # Ingest-time topic screen: "ai" keeps only items mentioning an AI/automation term,
    # "markets" keeps only items mentioning a markets/trading term. None -> no screen.
    screen: str | None = None


# Default keyword groups for the RSS ingest screen. Broad on purpose (a miss just costs one
# item); editable per-deployment via the `screen_keywords_ai` / `screen_keywords_markets`
# blocks in sources.yaml.
_DEFAULT_SCREEN_KEYWORDS_AI = [
    "ai", "artificial intelligence", "machine learning", "ml", "deep learning", "neural",
    "llm", "llms", "gpt", "generative", "algorithm", "algorithms", "algorithmic", "algo",
    "algos", "automation", "automated", "bot", "bots", "agent", "agents", "agentic",
    "copilot", "quant", "quantitative", "predictive", "data-driven",
]
_DEFAULT_SCREEN_KEYWORDS_MARKETS = [
    "trading", "trade", "trades", "trader", "traders", "market", "markets", "stock", "stocks",
    "equity", "equities", "share", "shares", "option", "options", "futures", "forex", "fx",
    "portfolio", "portfolios", "broker", "brokers", "brokerage", "exchange", "exchanges",
    "investing", "investment", "investments", "investor", "investors", "derivative",
    "derivatives", "etf", "etfs", "alpha", "backtest", "hedge fund", "crypto", "nifty",
    "sensex", "nse", "bse", "sebi", "zerodha", "upstox",
]


class RssSources(BaseModel):
    feeds: list[RssFeed] = Field(default_factory=list)
    screen_keywords_ai: list[str] = Field(default_factory=lambda: list(_DEFAULT_SCREEN_KEYWORDS_AI))
    screen_keywords_markets: list[str] = Field(
        default_factory=lambda: list(_DEFAULT_SCREEN_KEYWORDS_MARKETS)
    )


class ForumSource(BaseModel):
    name: str
    type: str = "html"  # "rss" | "html"
    url: str


class McpSources(BaseModel):
    github_search_queries: list[str] = Field(default_factory=list)


class TwitterSources(BaseModel):
    enabled: bool = False
    handles: list[str] = Field(default_factory=list)


class BlueskySources(BaseModel):
    enabled: bool = True
    queries: list[str] = Field(default_factory=list)


class NumeraiSources(BaseModel):
    enabled: bool = True
    forum_url: str = "https://forum.numer.ai"
    api_url: str = "https://api-tournament.numer.ai"
    leaderboard_size: int = 5


class StockTwitsSources(BaseModel):
    enabled: bool = False
    symbols: list[str] = Field(default_factory=list)
    stream_url: str = "https://firestream.stocktwits.com/symbols/stream"
    max_messages: int = 25
    poll_seconds: float = 10.0


class CareerBoard(BaseModel):
    firm: str
    ats: str            # "greenhouse" | "lever" | "ashby"
    token: str          # the firm's public board slug


class CareersSources(BaseModel):
    enabled: bool = False
    firms: list[CareerBoard] = Field(default_factory=list)


class Sources(BaseModel):
    github: GithubSources = Field(default_factory=GithubSources)
    reddit: RedditSources = Field(default_factory=RedditSources)
    rss: RssSources = Field(default_factory=RssSources)
    forums: list[ForumSource] = Field(default_factory=list)
    mcp: McpSources = Field(default_factory=McpSources)
    twitter: TwitterSources = Field(default_factory=TwitterSources)
    bluesky: BlueskySources = Field(default_factory=BlueskySources)
    numerai: NumeraiSources = Field(default_factory=NumeraiSources)
    stocktwits: StockTwitsSources = Field(default_factory=StockTwitsSources)
    careers: CareersSources = Field(default_factory=CareersSources)


@lru_cache
def get_settings() -> Settings:
    return Settings()


def _prune_none(value: Any) -> Any:
    """Drop keys whose value is None (an empty ``key:`` in YAML) so model defaults apply."""
    if isinstance(value, dict):
        return {k: _prune_none(v) for k, v in value.items() if v is not None}
    if isinstance(value, list):
        return [_prune_none(v) for v in value if v is not None]
    return value


@lru_cache
def get_sources() -> Sources:
    settings = get_settings()
    path = settings.resolve(settings.sources_file)
    if not path.exists():
        return Sources()
    data: dict[str, Any] = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    return Sources.model_validate(_prune_none(data))
