"""Generic OpenAI-compatible LLM provider.

Cerebras, Groq, and Google Gemini all expose OpenAI-compatible chat endpoints, so a single
adapter — parameterized by base URL, key, and model — serves all of them (and any future free
provider). It returns the same :class:`InsightExtraction` contract as the Claude adapter, so the
cascade can mix and match freely.
"""

from __future__ import annotations

import json

from loguru import logger
from openai import OpenAI

from ..config import COMMUNITY_SOURCES
from ..models import (
    Approach,
    Category,
    InsightExtraction,
    ItemType,
    RawItem,
    Region,
    WorkflowStage,
)
from .prompts import JSON_INSTRUCTION, SYSTEM_PROMPT, build_user_prompt

# case-insensitive lookup from any label -> canonical enum value
_CATEGORY_LOOKUP = {c.value.lower(): c.value for c in Category}
_APPROACH_LOOKUP = {a.value.lower(): a.value for a in Approach}
_ITEM_TYPE_LOOKUP = {t.value.lower(): t.value for t in ItemType}
_REGION_LOOKUP = {r.value.lower(): r.value for r in Region}
_WORKFLOW_LOOKUP = {w.value.lower(): w.value for w in WorkflowStage}

# Common synonyms a model might emit for the new axes (mapped to canonical enum values).
_ITEM_TYPE_LOOKUP.update({
    "product launch": ItemType.LAUNCH.value, "product": ItemType.LAUNCH.value,
    # A release / new feature comes from something that ALREADY exists → tooling, not a launch.
    "release": ItemType.TOOLING.value, "feature": ItemType.TOOLING.value,
    "fundraise": ItemType.FUNDING.value, "funding round": ItemType.FUNDING.value,
    "acquisition": ItemType.FUNDING.value, "raise": ItemType.FUNDING.value,
    "beta": ItemType.EARLY_STAGE.value, "waitlist": ItemType.EARLY_STAGE.value,
    "early stage": ItemType.EARLY_STAGE.value, "announced": ItemType.EARLY_STAGE.value,
    "job": ItemType.HIRING.value, "job posting": ItemType.HIRING.value,
    "career": ItemType.HIRING.value, "role": ItemType.HIRING.value,
    "vacancy": ItemType.HIRING.value, "opening": ItemType.HIRING.value,
    "paper": ItemType.RESEARCH.value, "thread": ItemType.DISCUSSION.value,
    "tool": ItemType.TOOLING.value, "library": ItemType.TOOLING.value,
    "infrastructure": ItemType.TOOLING.value, "update": ItemType.TOOLING.value,
})
_REGION_LOOKUP.update({
    "in": Region.INDIA.value, "indian": Region.INDIA.value,
    "global": Region.GLOBAL.value, "world": Region.GLOBAL.value, "us": Region.GLOBAL.value,
})
_WORKFLOW_LOOKUP.update({
    "signal": WorkflowStage.SIGNAL.value, "signals": WorkflowStage.SIGNAL.value,
    "signal generation": WorkflowStage.SIGNAL.value,
    "monitoring": WorkflowStage.MONITORING.value, "monitor": WorkflowStage.MONITORING.value,
    "risk management": WorkflowStage.RISK.value,
})


def _strip_fences(text: str) -> str:
    """Remove ```json … ``` fences some models wrap around JSON."""
    t = text.strip()
    if t.startswith("```"):
        t = t.split("\n", 1)[-1] if "\n" in t else t[3:]
        if t.endswith("```"):
            t = t[: -3]
    return t.strip()


def _normalize_category(value: object) -> str | None:
    if not isinstance(value, str):
        return None
    return _CATEGORY_LOOKUP.get(value.strip().lower())


def _normalize_approaches(value: object) -> list[str]:
    """Map the model's approach list to canonical values; drop unknowns, dedupe, cap at 3."""
    if isinstance(value, str):
        value = [value]
    if not isinstance(value, list):
        return []
    out: list[str] = []
    for raw in value:
        if not isinstance(raw, str):
            continue
        canon = _APPROACH_LOOKUP.get(raw.strip().lower())
        if canon and canon not in out:
            out.append(canon)
    return out[:3]


def _normalize_item_type(value: object, source: str) -> str:
    """Map to a canonical ItemType. Unknown/missing never drops the item: fall back to
    'discussion' for community sources, 'tooling' otherwise."""
    if isinstance(value, str):
        canon = _ITEM_TYPE_LOOKUP.get(value.strip().lower())
        if canon:
            return canon
    return ItemType.DISCUSSION.value if source in COMMUNITY_SOURCES else ItemType.TOOLING.value


def _normalize_region(value: object) -> str:
    if isinstance(value, str):
        canon = _REGION_LOOKUP.get(value.strip().lower())
        if canon:
            return canon
    return Region.GLOBAL.value


def _normalize_workflow_stage(value: object, item_type: str) -> str | None:
    """Only launch/funding/early_stage items carry a stage; unknown -> None (never fatal)."""
    if item_type not in {ItemType.LAUNCH.value, ItemType.FUNDING.value, ItemType.EARLY_STAGE.value}:
        return None
    if isinstance(value, str):
        return _WORKFLOW_LOOKUP.get(value.strip().lower())
    return None


class OpenAICompatProvider:
    """Turns a raw item into an :class:`InsightExtraction` via any OpenAI-compatible API."""

    def __init__(self, label: str, base_url: str, api_key: str, model: str):
        self.label = label
        self.model = model
        self.client = OpenAI(base_url=base_url, api_key=api_key)

    def extract(self, item: RawItem) -> InsightExtraction | None:
        content = f"{build_user_prompt(item)}\n\n{JSON_INSTRUCTION}"
        try:
            resp = self.client.chat.completions.create(
                model=self.model,
                messages=[
                    {"role": "system", "content": SYSTEM_PROMPT},
                    {"role": "user", "content": content},
                ],
                response_format={"type": "json_object"},
                temperature=0,
                max_tokens=800,
            )
        except Exception as exc:  # noqa: BLE001 — a failing/rate-limited provider falls through
            logger.warning(f"[{self.label}] request failed on item {item.id}: {exc}")
            return None

        raw = resp.choices[0].message.content if resp.choices else None
        if not raw:
            logger.warning(f"[{self.label}] empty response for item {item.id}.")
            return None

        try:
            data = json.loads(_strip_fences(raw))
        except (json.JSONDecodeError, TypeError):
            logger.warning(f"[{self.label}] non-JSON response for item {item.id}.")
            return None

        category = _normalize_category(data.get("category"))
        if category is None:
            logger.warning(f"[{self.label}] unrecognized category {data.get('category')!r}.")
            return None

        try:
            score = max(1, min(10, int(data.get("relevance_score"))))
        except (TypeError, ValueError):
            logger.warning(f"[{self.label}] invalid score {data.get('relevance_score')!r}.")
            return None

        item_type = _normalize_item_type(data.get("item_type"), item.source)
        region = _normalize_region(data.get("region"))
        workflow_stage = _normalize_workflow_stage(data.get("workflow_stage"), item_type)

        try:
            return InsightExtraction(
                relevance_score=score,
                category=Category(category),
                approaches=[Approach(a) for a in _normalize_approaches(data.get("approaches"))],
                item_type=ItemType(item_type),
                region=Region(region),
                workflow_stage=WorkflowStage(workflow_stage) if workflow_stage else None,
                technical_summary=str(data.get("technical_summary", "")).strip(),
                trader_impact=str(data.get("trader_impact", "")).strip(),
            )
        except Exception as exc:  # noqa: BLE001
            logger.warning(f"[{self.label}] validation failed for item {item.id}: {exc}")
            return None

    def summarize(self, prompt: str, *, system: str, max_tokens: int = 160) -> str | None:
        """Freeform text completion (no JSON mode) — used for the newsletter editorial pass."""
        try:
            resp = self.client.chat.completions.create(
                model=self.model,
                messages=[
                    {"role": "system", "content": system},
                    {"role": "user", "content": prompt},
                ],
                temperature=0.5,
                max_tokens=max_tokens,
            )
        except Exception as exc:  # noqa: BLE001 — a failing/rate-limited provider falls through
            logger.warning(f"[{self.label}] summarize request failed: {exc}")
            return None
        text = resp.choices[0].message.content if resp.choices else None
        return text.strip() if text else None
