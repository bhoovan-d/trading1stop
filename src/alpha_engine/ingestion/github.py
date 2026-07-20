"""GitHub ingestion: recent commits and releases across the tracked repos."""

from __future__ import annotations

from collections.abc import Iterable
from itertools import islice

from github import Auth, Github
from github.GithubException import GithubException
from loguru import logger
from tenacity import retry, stop_after_attempt, wait_exponential

from ..config import GithubSources, Settings
from .base import RawItemDraft, Source, truncate


def _client(settings: Settings) -> Github:
    if settings.github_token:
        return Github(auth=Auth.Token(settings.github_token), per_page=100)
    logger.warning("No GITHUB_TOKEN set — using unauthenticated GitHub (60 req/hr limit).")
    return Github(per_page=100)


class GithubSource(Source):
    source = "github"

    def __init__(self, settings: Settings, sources: GithubSources):
        self.settings = settings
        self.cfg = sources
        self.gh = _client(settings)

    @retry(stop=stop_after_attempt(3), wait=wait_exponential(min=1, max=10), reraise=True)
    def _repo(self, full_name: str):
        return self.gh.get_repo(full_name)

    def fetch(self) -> Iterable[RawItemDraft]:
        limit = self.settings.max_items_per_source
        track = set(self.cfg.track)
        for full_name in self.cfg.repos:
            try:
                repo = self._repo(full_name)
            except GithubException as exc:
                logger.error(f"[github] cannot access {full_name}: {exc}")
                continue

            if "commits" in track:
                yield from self._commits(repo, full_name, limit)
            if "releases" in track:
                yield from self._releases(repo, full_name, max(5, limit // 5))

    def _commits(self, repo, full_name: str, limit: int) -> Iterable[RawItemDraft]:
        try:
            for commit in islice(repo.get_commits(), limit):
                data = commit.commit
                message = data.message or ""
                author = None
                if commit.author is not None:
                    author = commit.author.login
                elif data.author is not None:
                    author = data.author.name
                title = message.splitlines()[0][:200] if message else commit.sha[:12]
                yield RawItemDraft(
                    source=self.source,
                    source_key=f"github:{full_name}",
                    external_id=f"{full_name}@{commit.sha}",
                    url=commit.html_url,
                    title=f"[{full_name}] {title}",
                    body=truncate(message),
                    author=author,
                    created_at=data.author.date if data.author else None,
                    raw={"repo": full_name, "sha": commit.sha, "kind": "commit"},
                )
        except GithubException as exc:
            logger.error(f"[github] commits for {full_name} failed: {exc}")

    def _releases(self, repo, full_name: str, limit: int) -> Iterable[RawItemDraft]:
        try:
            for rel in islice(repo.get_releases(), limit):
                title = rel.title or rel.tag_name or "release"
                yield RawItemDraft(
                    source=self.source,
                    source_key=f"github:{full_name}",
                    external_id=f"{full_name}#release:{rel.tag_name or rel.id}",
                    url=rel.html_url,
                    title=f"[{full_name}] release {rel.tag_name or ''} — {title}".strip(),
                    body=truncate(rel.body or ""),
                    author=(rel.author.login if rel.author else None),
                    created_at=rel.published_at or rel.created_at,
                    raw={"repo": full_name, "tag": rel.tag_name, "kind": "release"},
                )
        except GithubException as exc:
            logger.error(f"[github] releases for {full_name} failed: {exc}")
