"""Quant-firm / HFT careers ingestion from public applicant-tracking-system boards.

Reads a configured list of firms and pulls their open roles from whichever public ATS JSON
board they use (Greenhouse, Lever, or Ashby). Each posting reveals what a firm is building and
hiring for; the LLM later scores it under the "Quant Firms" category. Firm engineering blogs are
handled separately via the ordinary ``rss`` source, so this adapter is jobs-only.
"""

from __future__ import annotations

import time
from collections.abc import Iterable
from datetime import datetime, timezone
from html import unescape
import re

import httpx
from dateutil.parser import isoparse
from loguru import logger

from ..config import CareersSources, Settings
from .base import RawItemDraft, Source, truncate

_HTML_TAGS = re.compile(r"<[^>]+>")
_FETCH_DELAY_SECONDS = 1.0
_TIMEOUT = httpx.Timeout(20.0)
_HEADERS = {"User-Agent": "trading-alpha-engine/0.1 (+https://github.com/) careers"}

# Public, unauthenticated job-board endpoints. ``{token}`` is the firm's board slug.
_ENDPOINTS = {
    "greenhouse": "https://boards-api.greenhouse.io/v1/boards/{token}/jobs?content=true",
    "lever": "https://api.lever.co/v0/postings/{token}?mode=json",
    "ashby": "https://api.ashbyhq.com/posting-api/job-board/{token}?includeCompensation=true",
}


def _clean_html(value: str) -> str:
    # Greenhouse returns HTML-*escaped* content (e.g. "&lt;p&gt;"), so unescape FIRST to reveal the
    # real tags, then strip them; a final unescape catches entities that were inside the markup.
    text = _HTML_TAGS.sub(" ", unescape(value or ""))
    return re.sub(r"\s+", " ", unescape(text)).strip()


def _parse_time(value) -> datetime | None:
    """Parse an ISO string or an epoch-millis int (Lever) into an aware datetime."""
    if value is None or value == "":
        return None
    try:
        if isinstance(value, (int, float)):
            return datetime.fromtimestamp(value / 1000, tz=timezone.utc)
        return isoparse(str(value))
    except (TypeError, ValueError, OSError):
        return None


def _compose_body(description: str, meta: dict[str, str]) -> str:
    """Prepend location/team/department context to the description so the LLM can reason on it."""
    header = " · ".join(f"{k}: {v}" for k, v in meta.items() if v)
    parts = [p for p in (header, description) if p]
    return truncate("\n\n".join(parts))


class CareersSource(Source):
    source = "careers"

    def __init__(self, settings: Settings, sources: CareersSources):
        self.settings = settings
        self.cfg = sources

    def fetch(self) -> Iterable[RawItemDraft]:
        limit = self.settings.max_items_per_source
        for i, board in enumerate(self.cfg.firms):
            if i > 0:
                time.sleep(_FETCH_DELAY_SECONDS)
            ats = (board.ats or "").lower()
            template = _ENDPOINTS.get(ats)
            if template is None:
                logger.warning(f"[careers] {board.firm}: unknown ATS '{board.ats}' — skipping.")
                continue
            url = template.format(token=board.token)
            try:
                resp = httpx.get(url, headers=_HEADERS, timeout=_TIMEOUT, follow_redirects=True)
                resp.raise_for_status()
                payload = resp.json()
            except Exception as exc:  # noqa: BLE001
                logger.warning(f"[careers] {board.firm} ({ats}) fetch failed: {exc}")
                continue

            parser = getattr(self, f"_parse_{ats}")
            yield from parser(board, payload, limit)

    # --- per-ATS parsers ---------------------------------------------------------------------

    def _parse_greenhouse(self, board, payload, limit) -> Iterable[RawItemDraft]:
        for job in (payload.get("jobs") or [])[:limit]:
            job_id = str(job.get("id") or "")
            if not job_id:
                continue
            meta = {
                "Location": (job.get("location") or {}).get("name", ""),
                "Department": ", ".join(
                    d.get("name", "") for d in (job.get("departments") or [])
                ),
            }
            yield self._draft(
                board,
                job_id=job_id,
                title=job.get("title") or "untitled",
                url=job.get("absolute_url") or "",
                description=_clean_html(job.get("content") or ""),
                meta=meta,
                created_at=_parse_time(job.get("updated_at")),
            )

    def _parse_lever(self, board, payload, limit) -> Iterable[RawItemDraft]:
        for job in (payload or [])[:limit]:
            job_id = str(job.get("id") or "")
            if not job_id:
                continue
            cats = job.get("categories") or {}
            meta = {
                "Location": cats.get("location", ""),
                "Team": cats.get("team", ""),
                "Department": cats.get("department", ""),
                "Commitment": cats.get("commitment", ""),
            }
            description = job.get("descriptionPlain") or _clean_html(job.get("description") or "")
            yield self._draft(
                board,
                job_id=job_id,
                title=job.get("text") or "untitled",
                url=job.get("hostedUrl") or job.get("applyUrl") or "",
                description=description,
                meta=meta,
                created_at=_parse_time(job.get("createdAt")),
            )

    def _parse_ashby(self, board, payload, limit) -> Iterable[RawItemDraft]:
        for job in (payload.get("jobs") or [])[:limit]:
            job_id = str(job.get("id") or "")
            if not job_id:
                continue
            meta = {
                "Location": job.get("location", ""),
                "Team": job.get("team", ""),
                "Department": job.get("department", ""),
                "Type": job.get("employmentType", ""),
            }
            description = job.get("descriptionPlain") or _clean_html(job.get("descriptionHtml") or "")
            yield self._draft(
                board,
                job_id=job_id,
                title=job.get("title") or "untitled",
                url=job.get("jobUrl") or job.get("applyUrl") or "",
                description=description,
                meta=meta,
                created_at=_parse_time(job.get("publishedAt")),
            )

    # --- shared draft builder ----------------------------------------------------------------

    def _draft(self, board, *, job_id, title, url, description, meta, created_at) -> RawItemDraft:
        clean_meta = {k: v for k, v in meta.items() if v}
        return RawItemDraft(
            source=self.source,
            external_id=f"careers:{board.ats}:{board.token}:{job_id}",
            url=url,
            title=f"[{board.firm}] {title}",
            body=_compose_body(description, clean_meta),
            author=board.firm,
            created_at=created_at,
            raw={"firm": board.firm, "ats": board.ats, **clean_meta},
        )
