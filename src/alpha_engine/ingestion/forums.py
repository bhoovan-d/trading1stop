"""Forum ingestion. QuantConnect gets a dedicated scraper; other forums use a generic
RSS-then-HTML fallback.

QuantConnect's forum has no RSS and no recent-sorted endpoint — its ``/forum/list/{page}/
community/`` pages are ordered oldest-first over ~1000 pages, so the newest threads live on
the *last* page. We discover the last page with a bounded binary search, then pull the newest
threads and use each thread's meta description as the body. It's heavier than other sources but
runs once per day and is fully wrapped in try/except, so any breakage is skipped, never fatal.

Forums are a *community-stream* source (discussion, not shipped engineering) and are held to a
lower relevance bar.
"""

from __future__ import annotations

import re
from collections.abc import Iterable
from urllib.parse import urljoin, urlparse

import feedparser
import httpx
from loguru import logger
from selectolax.parser import HTMLParser

from ..config import ForumSource as ForumCfg
from ..config import Settings
from .base import RawItemDraft, Source, truncate

_HEADERS = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) trading-alpha-engine/0.1"}
_THREAD_HINTS = ("/forum/", "/discussion", "/discussions/", "/thread", "/topic")
_QC_DISCUSSION_RE = re.compile(r"/forum/discussion/(\d+)/")
_QC_MAX_PROBES = 16  # bound the last-page binary search


class ForumSource(Source):
    source = "forum"

    def __init__(self, settings: Settings, forums: list[ForumCfg]):
        self.settings = settings
        self.forums = forums

    def fetch(self) -> Iterable[RawItemDraft]:
        limit = self.settings.max_items_per_source
        for forum in self.forums:
            try:
                if "quantconnect.com" in urlparse(forum.url).netloc:
                    yield from self._quantconnect(forum, min(limit, 12))
                    continue
                if forum.type == "rss":
                    items = list(self._via_rss(forum, limit))
                    if items:
                        yield from items
                        continue
                    logger.info(f"[forum] {forum.name}: no RSS entries, trying HTML.")
                yield from self._via_html(forum, limit)
            except Exception as exc:  # noqa: BLE001 — one bad forum must not sink the run
                logger.error(f"[forum] {forum.name} failed: {exc}")

    # ---- QuantConnect ---------------------------------------------------------

    def _qc_threads_on(self, base: str, page: int) -> list[tuple[int, str, str]]:
        html = httpx.get(
            f"{base}/forum/list/{page}/community/", headers=_HEADERS, timeout=20.0, follow_redirects=True
        ).text
        out: list[tuple[int, str, str]] = []
        tree = HTMLParser(html)
        for a in tree.css("a"):
            href = a.attributes.get("href") or ""
            m = _QC_DISCUSSION_RE.search(href)
            text = (a.text() or "").strip()
            if m and text:
                out.append((int(m.group(1)), text, urljoin(base, href)))
        return out

    def _qc_last_page(self, base: str) -> int:
        """Bounded binary search for the highest page that still has threads (= newest)."""
        probes = 0
        lo, hi = 1, 2
        # exponential: grow hi until it's empty
        while probes < _QC_MAX_PROBES and self._qc_threads_on(base, hi):
            lo, hi = hi, hi * 2
            probes += 1
        # binary search the boundary in (lo, hi]
        while lo + 1 < hi and probes < _QC_MAX_PROBES:
            mid = (lo + hi) // 2
            if self._qc_threads_on(base, mid):
                lo = mid
            else:
                hi = mid
            probes += 1
        return lo

    def _qc_body(self, url: str) -> str:
        try:
            html = httpx.get(url, headers=_HEADERS, timeout=20.0, follow_redirects=True).text
            tree = HTMLParser(html)
            for sel in ('meta[property="og:description"]', 'meta[name="description"]'):
                node = tree.css_first(sel)
                if node and (node.attributes.get("content") or "").strip():
                    return node.attributes["content"].strip()
        except Exception:  # noqa: BLE001
            pass
        return ""

    def _quantconnect(self, forum: ForumCfg, limit: int) -> Iterable[RawItemDraft]:
        base = f"{urlparse(forum.url).scheme}://{urlparse(forum.url).netloc}"
        last = self._qc_last_page(base)
        # newest threads are the highest ids across the last couple of pages
        collected: dict[int, tuple[str, str]] = {}
        for page in (last, last - 1):
            if page < 1:
                continue
            for tid, title, url in self._qc_threads_on(base, page):
                collected[tid] = (title, url)
            if len(collected) >= limit:
                break

        newest = sorted(collected.items(), key=lambda kv: kv[0], reverse=True)[:limit]
        logger.info(f"[forum] {forum.name}: last page {last}, {len(newest)} newest threads.")
        for tid, (title, url) in newest:
            yield RawItemDraft(
                source=self.source,
                external_id=f"forum:qc:{tid}",
                url=url,
                title=f"[{forum.name}] {title[:200]}",
                body=truncate(self._qc_body(url)),
                raw={"forum": forum.name, "via": "qc-list", "id": tid},
            )

    # ---- generic fallback -----------------------------------------------------

    def _via_rss(self, forum: ForumCfg, limit: int) -> Iterable[RawItemDraft]:
        parsed = feedparser.parse(forum.url)
        for entry in parsed.entries[:limit]:
            link = getattr(entry, "link", "") or ""
            ext_id = getattr(entry, "id", "") or link
            if not ext_id:
                continue
            yield RawItemDraft(
                source=self.source,
                external_id=f"forum:{ext_id}",
                url=link,
                title=f"[{forum.name}] {getattr(entry, 'title', 'thread')}",
                body=truncate(getattr(entry, "summary", "")),
                author=getattr(entry, "author", None),
                raw={"forum": forum.name, "via": "rss"},
            )

    def _via_html(self, forum: ForumCfg, limit: int) -> Iterable[RawItemDraft]:
        resp = httpx.get(forum.url, headers=_HEADERS, timeout=20.0, follow_redirects=True)
        resp.raise_for_status()
        tree = HTMLParser(resp.text)
        base = f"{urlparse(forum.url).scheme}://{urlparse(forum.url).netloc}"

        seen: set[str] = set()
        count = 0
        for node in tree.css("a"):
            if count >= limit:
                break
            href = node.attributes.get("href") or ""
            text = (node.text() or "").strip()
            if not href or len(text) < 15:
                continue
            if not any(h in href for h in _THREAD_HINTS):
                continue
            url = urljoin(base, href)
            if url in seen:
                continue
            seen.add(url)
            count += 1
            yield RawItemDraft(
                source=self.source,
                external_id=f"forum:{url}",
                url=url,
                title=f"[{forum.name}] {text[:200]}",
                body="",
                raw={"forum": forum.name, "via": "html"},
            )
