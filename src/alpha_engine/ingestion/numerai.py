"""Public Numerai tournament and forum ingestion."""

from __future__ import annotations

from collections.abc import Iterable
from datetime import datetime
from html import unescape
import re

import httpx
from dateutil.parser import isoparse
from loguru import logger

from ..config import NumeraiSources, Settings
from .base import RawItemDraft, Source, truncate

_TOURNAMENT_QUERY = """
query TournamentSnapshot {
  rounds(tournament: 8, number: 0) { number openTime resolveTime }
  v2Leaderboard { username rank }
}
"""
_HTML_TAGS = re.compile(r"<[^>]+>")


def _parse_time(value: str | None) -> datetime | None:
    try:
        return isoparse(value) if value else None
    except (TypeError, ValueError):
        return None


def _clean_html(value: str) -> str:
    return unescape(_HTML_TAGS.sub(" ", value or "")).strip()


class NumeraiSource(Source):
    """Emit tournament snapshots and newest public forum topics as alpha-stream items."""

    source = "numerai"

    def __init__(self, settings: Settings, sources: NumeraiSources):
        self.settings = settings
        self.cfg = sources

    def fetch(self) -> Iterable[RawItemDraft]:
        yield from self._tournament_items()
        yield from self._forum_items()

    def _tournament_items(self) -> Iterable[RawItemDraft]:
        try:
            response = httpx.post(self.cfg.api_url, json={"query": _TOURNAMENT_QUERY}, timeout=20.0)
            response.raise_for_status()
            response_payload = response.json()
            if response_payload.get("errors"):
                raise ValueError(response_payload["errors"])
            payload = response_payload.get("data") or {}
        except Exception as exc:  # noqa: BLE001
            logger.warning(f"[numerai] tournament API failed: {exc}")
            return

        round_data = (payload.get("rounds") or [{}])[0]
        number = round_data.get("number")
        if number is not None:
            body = "\n".join(
                f"{label}: {round_data[key]}"
                for label, key in (("Open", "openTime"), ("Resolve", "resolveTime"))
                if round_data.get(key)
            )
            yield RawItemDraft(
                source=self.source,
                external_id=f"numerai:round:{number}",
                url="https://numer.ai/rounds",
                title=f"Numerai tournament round {number}",
                body=body,
                created_at=_parse_time(round_data.get("openTime")),
                raw={"kind": "round", "round": round_data},
            )

        leaderboard = payload.get("v2Leaderboard") or []
        for entry in leaderboard[: self.cfg.leaderboard_size]:
            username = entry.get("username") or entry.get("modelName")
            if not username or number is None:
                continue
            rank = entry.get("rank")
            yield RawItemDraft(
                source=self.source,
                external_id=f"numerai:leaderboard:{number}:{username}",
                url="https://numer.ai/leaderboard",
                title=f"Numerai round {number} leaderboard: {username}",
                body=f"Rank: {rank}\nReputation: {entry.get('reputation')}\nStake: {entry.get('stake')}",
                raw={"kind": "leaderboard", "round": number, "entry": entry},
            )

    def _forum_items(self) -> Iterable[RawItemDraft]:
        try:
            response = httpx.get(f"{self.cfg.forum_url.rstrip('/')}/latest.json", timeout=20.0)
            response.raise_for_status()
            topics = (response.json().get("topic_list") or {}).get("topics") or []
        except Exception as exc:  # noqa: BLE001
            logger.warning(f"[numerai] forum API failed: {exc}")
            return

        for topic in topics[: self.settings.max_items_per_source]:
            topic_id = topic.get("id")
            slug = topic.get("slug") or "topic"
            if not topic_id:
                continue
            excerpt = _clean_html(topic.get("excerpt") or "")
            yield RawItemDraft(
                source=self.source,
                external_id=f"numerai:forum:{topic_id}",
                url=f"{self.cfg.forum_url.rstrip('/')}/t/{slug}/{topic_id}",
                title=f"[Numerai Forum] {topic.get('title') or 'Untitled'}",
                body=truncate(excerpt),
                author=topic.get("last_poster_username"),
                created_at=_parse_time(topic.get("created_at") or topic.get("last_posted_at")),
                raw={"kind": "forum", "topic": topic},
            )
