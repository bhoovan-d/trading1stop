"""Optional, bounded StockTwits Firestream ingestion."""

from __future__ import annotations

from collections.abc import Iterable
import json

import httpx
from dateutil.parser import isoparse
from loguru import logger

from ..config import Settings, StockTwitsSources
from .base import RawItemDraft, Source, truncate


class StockTwitsSource(Source):
    source = "stocktwits"

    def __init__(self, settings: Settings, sources: StockTwitsSources):
        self.settings = settings
        self.cfg = sources

    def fetch(self) -> Iterable[RawItemDraft]:
        enabled = self.settings.stocktwits_enabled and self.cfg.enabled
        if not enabled:
            logger.info("[stocktwits] disabled — skipping (set STOCKTWITS_ENABLED=true to enable).")
            return []
        if not self.settings.stocktwits_username or not self.settings.stocktwits_password:
            logger.warning("[stocktwits] enabled but credentials are missing — skipping.")
            return []
        return self._fetch_enabled()

    def _fetch_enabled(self) -> Iterable[RawItemDraft]:
        symbols = {symbol.upper() for symbol in self.cfg.symbols}
        seen: set[str] = set()
        emitted = 0
        try:
            with httpx.stream(
                "GET",
                self.cfg.stream_url,
                auth=(self.settings.stocktwits_username or "", self.settings.stocktwits_password or ""),
                headers={"Accept": "text/event-stream", "Accept-Encoding": "gzip"},
                timeout=httpx.Timeout(connect=20.0, read=self.cfg.poll_seconds, write=20.0, pool=20.0),
            ) as response:
                response.raise_for_status()
                for line in response.iter_lines():
                    if not line.startswith("data:"):
                        continue
                    try:
                        event = json.loads(line[5:].strip())
                    except json.JSONDecodeError:
                        continue
                    symbol = str(event.get("symbol") or "").upper()
                    if symbols and symbol not in symbols:
                        continue
                    event_id = str(event.get("id") or event.get("seq_id") or "")
                    if not event_id or event_id in seen:
                        continue
                    seen.add(event_id)
                    message = event.get("body") or event.get("text") or event.get("metric") or "StockTwits event"
                    created_at = None
                    try:
                        created_at = isoparse(event["created_at"]) if event.get("created_at") else None
                    except (TypeError, ValueError):
                        pass
                    yield RawItemDraft(
                        source=self.source,
                        external_id=f"stocktwits:{event_id}",
                        url=event.get("url") or f"https://stocktwits.com/symbol/{symbol}",
                        title=f"[${symbol}] {str(message)[:200]}",
                        body=truncate(str(message)),
                        author=str(event.get("username") or event.get("user_id") or "") or None,
                        created_at=created_at,
                        raw={"symbol": symbol, "sentiment": event.get("sentiment"), "event": event},
                    )
                    emitted += 1
                    if emitted >= min(self.cfg.max_messages, self.settings.max_items_per_source):
                        return
        except Exception as exc:  # noqa: BLE001
            logger.warning(f"[stocktwits] stream failed: {exc}")
