"""Build the list of active ingestion sources from config."""

from __future__ import annotations

from ..config import GithubSources, Settings, Sources
from ..db import session_scope
from ..storage.repository import active_github_targets
from .base import Source
from .bluesky import BlueskySource
from .careers import CareersSource
from .forums import ForumSource
from .github import GithubSource
from .mcp_discovery import McpDiscoverySource
from .reddit import RedditSource
from .rss import RssSource
from .numerai import NumeraiSource
from .stocktwits import StockTwitsSource
from .twitter import TwitterSource

# Ordered names -> builder(settings, sources) -> Source | None
_BUILDERS = {
    "github": lambda s, src: GithubSource(s, src.github) if src.github.repos else None,
    "reddit": lambda s, src: RedditSource(s, src.reddit) if src.reddit.subreddits else None,
    "rss": lambda s, src: RssSource(s, src.rss) if src.rss.feeds else None,
    "forum": lambda s, src: ForumSource(s, src.forums) if src.forums else None,
    "mcp": lambda s, src: McpDiscoverySource(s, src.mcp) if src.mcp.github_search_queries else None,
    "twitter": lambda s, src: TwitterSource(s, src.twitter),
    "bluesky": lambda s, src: BlueskySource(s, src.bluesky) if src.bluesky.enabled and src.bluesky.queries else None,
    "numerai": lambda s, src: NumeraiSource(s, src.numerai) if src.numerai.enabled else None,
    "stocktwits": lambda s, src: StockTwitsSource(s, src.stocktwits),
    "careers": lambda s, src: CareersSource(s, src.careers) if src.careers.enabled and src.careers.firms else None,
}

SOURCE_NAMES = list(_BUILDERS)


def build_sources(
    settings: Settings, sources: Sources, only: list[str] | None = None
) -> list[Source]:
    """Instantiate the configured sources. ``only`` restricts to specific source names."""
    names = only or SOURCE_NAMES
    # Promoted discovery candidates become regular GitHub ingestion targets without editing YAML.
    if "github" in names:
        with session_scope() as session:
            dynamic = active_github_targets(session)
        configured = list(sources.github.repos)
        if dynamic:
            sources = sources.model_copy(update={
                "github": GithubSources(track=sources.github.track, repos=list(dict.fromkeys(configured + dynamic)))
            })
    built: list[Source] = []
    for name in names:
        builder = _BUILDERS.get(name)
        if builder is None:
            continue
        adapter = builder(settings, sources)
        if adapter is not None:
            built.append(adapter)
    return built
