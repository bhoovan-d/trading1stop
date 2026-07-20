"""Discover market-data MCP (Model Context Protocol) servers via GitHub search."""

from __future__ import annotations

from collections.abc import Iterable
from itertools import islice

from github.GithubException import GithubException
from loguru import logger

from ..config import McpSources, Settings
from .base import RawItemDraft, Source, truncate
from .github import _client


class McpDiscoverySource(Source):
    source = "mcp"

    def __init__(self, settings: Settings, sources: McpSources):
        self.settings = settings
        self.cfg = sources
        self.gh = _client(settings)

    def fetch(self) -> Iterable[RawItemDraft]:
        limit = max(5, self.settings.max_items_per_source // 3)
        seen: set[str] = set()
        for query in self.cfg.github_search_queries:
            try:
                results = self.gh.search_repositories(query=query, sort="updated")
                for repo in islice(results, limit):
                    if repo.full_name in seen:
                        continue
                    seen.add(repo.full_name)
                    desc = repo.description or ""
                    yield RawItemDraft(
                        source=self.source,
                        source_key=f"github:{repo.full_name}",
                        external_id=f"mcp:{repo.full_name}",
                        url=repo.html_url,
                        title=f"[MCP] {repo.full_name}",
                        body=truncate(
                            f"{desc}\n\nStars: {repo.stargazers_count} · "
                            f"Language: {repo.language} · Updated: {repo.updated_at}\n"
                            f"Topics: {', '.join(repo.get_topics() or [])}"
                        ),
                        author=(repo.owner.login if repo.owner else None),
                        created_at=repo.pushed_at or repo.updated_at,
                        raw={"query": query, "full_name": repo.full_name, "kind": "github_repo_candidate"},
                    )
            except GithubException as exc:
                logger.error(f"[mcp] search '{query}' failed: {exc}")
