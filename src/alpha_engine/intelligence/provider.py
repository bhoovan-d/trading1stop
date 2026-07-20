"""Provider-agnostic LLM layer.

The pipeline talks only to :class:`LLMProvider`. A :class:`CascadeProvider` tries an ordered
list of providers until one returns a valid insight — this is the seam a future *free-LLM
cascade* plugs into: implement the protocol, register it in ``_FACTORIES``, and list it in
``LLM_PROVIDER_CHAIN``. No pipeline code changes required.
"""

from __future__ import annotations

import itertools
from typing import Callable, Protocol, runtime_checkable

from loguru import logger

from ..config import Settings
from ..models import InsightExtraction, RawItem


@runtime_checkable
class LLMProvider(Protocol):
    """Anything that can turn a raw item into a structured insight (or decline)."""

    label: str

    def extract(self, item: RawItem) -> InsightExtraction | None:
        """Return the structured extraction, or None to fall through to the next provider."""
        ...

    def summarize(self, prompt: str, *, system: str, max_tokens: int = 160) -> str | None:
        """Optional: return a freeform text completion, or None to fall through.

        Not every provider must implement this; the cascade skips those that don't.
        """
        ...


class CascadeProvider:
    """Try providers until one returns a result. The starting provider rotates per call.

    Rotation matters under concurrent synthesis: without it every worker would prefer the
    same first provider and stampede it into rate limits while the others idle. Rotating the
    start index spreads the base load across all configured providers (round-robin), and the
    remaining providers still act as fallbacks on any failure/rate-limit. ``itertools.count``
    is atomic under the GIL, so the rotation is thread-safe.
    """

    label = "cascade"

    def __init__(self, providers: list[LLMProvider]):
        self.providers = providers
        self._rotation = itertools.count()

    def extract(self, item: RawItem) -> tuple[InsightExtraction, str] | None:
        n = len(self.providers)
        if n == 0:
            return None
        start = next(self._rotation) % n
        ordered = self.providers[start:] + self.providers[:start]
        for provider in ordered:
            try:
                result = provider.extract(item)
            except Exception as exc:  # noqa: BLE001 — a bad provider must not stop the cascade
                logger.warning(f"[llm] provider {provider.label} errored: {exc}")
                continue
            if result is not None:
                logger.debug(f"[llm] item {item.id} served by {provider.label}")
                return result, provider.label
        return None

    def summarize(self, prompt: str, *, system: str, max_tokens: int = 160) -> tuple[str, str] | None:
        """Freeform completion across the cascade; returns (text, provider_label) or None.

        Rotates the starting provider and falls through on error/empty, exactly like
        :meth:`extract`. Providers that don't implement ``summarize`` are skipped.
        """
        n = len(self.providers)
        if n == 0:
            return None
        start = next(self._rotation) % n
        ordered = self.providers[start:] + self.providers[:start]
        for provider in ordered:
            fn = getattr(provider, "summarize", None)
            if fn is None:
                continue
            try:
                text = fn(prompt, system=system, max_tokens=max_tokens)
            except Exception as exc:  # noqa: BLE001 — a bad provider must not stop the cascade
                logger.warning(f"[llm] provider {provider.label} summarize errored: {exc}")
                continue
            if text:
                return text, provider.label
        return None

    @property
    def available(self) -> bool:
        return bool(self.providers)


def _build_anthropic(settings: Settings) -> LLMProvider | None:
    if not settings.anthropic_api_key:
        logger.warning("[llm] ANTHROPIC_API_KEY not set — Claude provider unavailable.")
        return None
    from .anthropic_provider import AnthropicProvider

    return AnthropicProvider(settings)


def _build_openai_compat(name: str, api_key: str | None, base_url: str, model: str) -> LLMProvider | None:
    if not api_key:
        logger.warning(f"[llm] {name.upper()}_API_KEY not set — {name} provider unavailable.")
        return None
    from .openai_compat_provider import OpenAICompatProvider

    return OpenAICompatProvider(label=f"{name}:{model}", base_url=base_url, api_key=api_key, model=model)


# name -> factory. All free providers share the OpenAI-compatible adapter; add more free
# providers by dropping another line here + a key in .env, and listing it in LLM_PROVIDER_CHAIN.
_FACTORIES: dict[str, Callable[[Settings], LLMProvider | None]] = {
    "cerebras": lambda s: _build_openai_compat("cerebras", s.cerebras_api_key, s.cerebras_base_url, s.cerebras_model),
    "groq": lambda s: _build_openai_compat("groq", s.groq_api_key, s.groq_base_url, s.groq_model),
    "gemini": lambda s: _build_openai_compat("gemini", s.gemini_api_key, s.gemini_base_url, s.gemini_model),
    "sambanova": lambda s: _build_openai_compat("sambanova", s.sambanova_api_key, s.sambanova_base_url, s.sambanova_model),
    "openrouter": lambda s: _build_openai_compat("openrouter", s.openrouter_api_key, s.openrouter_base_url, s.openrouter_model),
    "anthropic": _build_anthropic,
}


def build_provider(settings: Settings) -> CascadeProvider:
    providers: list[LLMProvider] = []
    for name in settings.provider_chain:
        factory = _FACTORIES.get(name)
        if factory is None:
            logger.warning(f"[llm] unknown provider '{name}' in LLM_PROVIDER_CHAIN — skipping.")
            continue
        provider = factory(settings)
        if provider is not None:
            providers.append(provider)
    if not providers:
        logger.warning("[llm] no usable LLM providers configured — synthesis will be skipped.")
    return CascadeProvider(providers)
