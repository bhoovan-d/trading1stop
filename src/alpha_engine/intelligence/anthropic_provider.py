"""Reference LLM provider: Anthropic Claude with structured output + prompt caching."""

from __future__ import annotations

import anthropic
from loguru import logger

from ..config import Settings
from ..models import InsightExtraction, RawItem
from .prompts import SYSTEM_PROMPT, build_user_prompt


class AnthropicProvider:
    """Turns a raw item into an :class:`InsightExtraction` via Claude structured outputs.

    The system prompt (the taxonomy + scoring rubric) is stable across every call, so it is
    marked for prompt caching to keep the daily batch cheap.
    """

    def __init__(self, settings: Settings):
        self.settings = settings
        self.model = settings.anthropic_model
        self.label = f"anthropic:{self.model}"
        self.client = anthropic.Anthropic(api_key=settings.anthropic_api_key)

    def extract(self, item: RawItem) -> InsightExtraction | None:
        try:
            resp = self.client.messages.parse(
                model=self.model,
                max_tokens=1024,
                system=[
                    {
                        "type": "text",
                        "text": SYSTEM_PROMPT,
                        "cache_control": {"type": "ephemeral"},
                    }
                ],
                messages=[{"role": "user", "content": build_user_prompt(item)}],
                output_format=InsightExtraction,
            )
        except anthropic.APIError as exc:
            logger.warning(f"[anthropic] API error on item {item.id}: {exc}")
            return None

        if getattr(resp, "stop_reason", None) == "refusal":
            logger.info(f"[anthropic] refusal on item {item.id}; skipping.")
            return None

        extraction = getattr(resp, "parsed_output", None)
        if extraction is None:
            logger.warning(f"[anthropic] no parsed output for item {item.id}.")
            return None

        # Score range isn't enforceable in the JSON schema; clamp defensively.
        extraction.relevance_score = max(1, min(10, int(extraction.relevance_score)))
        return extraction

    def summarize(self, prompt: str, *, system: str, max_tokens: int = 160) -> str | None:
        """Freeform text completion — used for the newsletter editorial pass."""
        try:
            resp = self.client.messages.create(
                model=self.model,
                max_tokens=max_tokens,
                system=system,
                messages=[{"role": "user", "content": prompt}],
            )
        except anthropic.APIError as exc:
            logger.warning(f"[anthropic] summarize API error: {exc}")
            return None
        parts = [b.text for b in resp.content if getattr(b, "type", None) == "text"]
        text = "".join(parts).strip()
        return text or None
