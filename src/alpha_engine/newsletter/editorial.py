"""LLM-written editorial layer for the daily brief (theme + editor's note + per-pick copy).

Called once at newsletter-write time (never on API reads). Given the day's tiered picks, it
asks the provider cascade to (1) write a focused one-line theme and (2) translate the dense,
technical insight fields into accessible, informative editorial prose plus a short editor's
note. The theme is a separate, single-purpose call because a focused prompt yields far sharper
headlines than folding it into the larger editorial request. Returns a JSON payload keyed by
insight id so the renderer can fall back per-pick to the raw technical fields whenever a piece
of editorial copy is missing. Degrades to None when no provider is configured or every call
fails — the renderer then uses the technical fields and a deterministic tagline.
"""

from __future__ import annotations

import json

from ..intelligence.provider import CascadeProvider
from ..models import Insight, RawItem

Row = tuple[Insight, RawItem]

THEME_SYSTEM_PROMPT = """\
You are the editor of a daily intelligence brief on how AI/ML is reshaping the trading process, \
read by independent and retail algo-traders. Your voice is calm, editorial, and curated — never \
hype, never marketing.

Write ONE sentence (18-28 words) naming the concrete through-line across today's headline picks. \
Be specific: reference the actual techniques, capabilities, or shift in the picks (e.g. neural \
SDEs, agentic research pipelines, inverse-RL risk elicitation) — not vague abstractions.

Hard rules:
- BANNED openings and phrases: "Advances in", "AI-driven", "AI and ML", "This brief", "Today's", \
  "In the world of", "The rise of", "developments", "innovations", "reshaping", "competitive \
  edge". Anything that could headline any day's brief is a failure.
- Name the specific thread. If the picks share a real theme, state it; if they span distinct \
  fronts, say what those fronts are.
- No greeting, no meta-commentary, no markdown, no surrounding quotes.

Examples of the register (do not reuse verbatim):
- "Neural-operator methods are quietly displacing Markovian SDEs in hedging and execution, while \
  agentic frameworks push research-to-backtest toward full automation."
- "Risk tooling turns introspective — inverse RL now reverse-engineers desk risk appetite \
  straight from execution logs."

Return only the sentence.
"""

EDITORIAL_SYSTEM_PROMPT = """\
You are the editor of a daily intelligence brief on how AI/ML is reshaping the trading process. \
Your readers are independent and retail algo-traders — technically literate but NOT academics. \
Your voice is calm, editorial, and curated: you explain, you never hype or market.

Your job: turn dense, jargon-heavy research notes into clear, informative editorial copy. For \
every pick, explain in plain language WHAT it is and WHY a trader should care — the capability, \
edge, or risk it changes. Translate or omit jargon (no bare terms like "H^2_T", "Malliavin-\
Sobolev", "square-integrable predictable processes"); if a concept matters, explain it in a few \
plain words. Lead with meaning, not mechanism. Be concrete and specific to each pick — never \
generic filler.

You will receive today's picks, each with an id, a tier (lead | notable | in_brief), and its raw \
technical notes. Return STRICT JSON and nothing else — no markdown fences, no prose around it — \
in exactly this shape:
{
  "editor_note": "<2-3 sentences of narrative synthesis>",
  "picks": {
    "<id>": {"summary": "<editorial copy for that pick>"}
  }
}

EDITOR'S NOTE rules: 2-3 sentences that name the SPECIFIC threads connecting today's picks and \
why they matter now. BANNED filler: "significant developments", "gain a more nuanced \
understanding", "make more informed decisions", "reduce operational costs", "competitive edge", \
"stay ahead", "leveraging these". Say something a knowledgeable editor would actually write.
Example of the register: "Two currents run through today's picks: neural-operator models are \
maturing into practical hedging tools, and agentic frameworks are closing the loop from research \
to backtest. Both chip away at work desks still do by hand."

Length per tier: lead summary = 2-4 informative sentences; notable summary = 1 sentence; \
in_brief summary = 1 short clause (under ~20 words). Include every pick id you are given. Do not \
restate the title. No trailing commentary outside the JSON.
"""


def build_theme_prompt(picks: list[Row]) -> str:
    lines = ["Today's headline picks:", ""]
    for insight, raw in picks:
        lines.append(f"- [{insight.category}] {raw.title}")
        lines.append(f"  Why it matters: {insight.trader_impact.strip()}")
    lines.append("")
    lines.append("Write the single-sentence theme.")
    return "\n".join(lines)


def _pick_lines(insight: Insight, raw: RawItem, tier: str) -> list[str]:
    return [
        f"- id: {insight.id}",
        f"  tier: {tier}",
        f"  category: {insight.category}",
        f"  title: {raw.title}",
        f"  technical_notes: {insight.technical_summary.strip()}",
        f"  trader_impact: {insight.trader_impact.strip()}",
    ]


def build_editorial_prompt(lead: list[Row], notable: list[Row], in_brief: list[Row]) -> str:
    lines = ["Today's picks:", ""]
    for tier, rows in (("lead", lead), ("notable", notable), ("in_brief", in_brief)):
        for insight, raw in rows:
            lines += _pick_lines(insight, raw, tier)
    lines.append("")
    lines.append("Return the JSON editorial payload.")
    return "\n".join(lines)


def _strip_fences(text: str) -> str:
    """Remove ```json … ``` fences some models wrap around JSON (mirrors the provider helper)."""
    t = text.strip()
    if t.startswith("```"):
        t = t.split("\n", 1)[-1] if "\n" in t else t[3:]
        if t.endswith("```"):
            t = t[:-3]
    return t.strip()


def _clean(text: str) -> str:
    return " ".join(text.split()).strip()


def _parse_body(text: str) -> dict:
    """Parse the editor_note + picks JSON body; return {} on any failure (safe fallback)."""
    try:
        data = json.loads(_strip_fences(text))
    except (json.JSONDecodeError, TypeError):
        return {}
    if not isinstance(data, dict):
        return {}
    out: dict = {}
    note = data.get("editor_note")
    if isinstance(note, str) and note.strip():
        out["editor_note"] = _clean(note)
    picks: dict[str, dict] = {}
    picks_in = data.get("picks")
    if isinstance(picks_in, dict):
        for key, val in picks_in.items():
            summary = val.get("summary") if isinstance(val, dict) else val
            if isinstance(summary, str) and summary.strip():
                picks[str(key)] = {"summary": _clean(summary)}
    out["picks"] = picks
    return out


def generate_editorial(
    lead: list[Row],
    notable: list[Row],
    in_brief: list[Row],
    provider: CascadeProvider,
) -> tuple[dict, str] | None:
    """Return (payload, model_used) for the day's picks, or None if unavailable/all failed.

    Two calls: a focused theme call (sharper headlines) and one editorial call for the note +
    per-pick copy. Each degrades independently; a payload is returned if either succeeds.
    """
    picks = lead + notable + in_brief
    if not picks or not provider.available:
        return None

    payload: dict = {"picks": {}}
    model_used = ""

    theme_res = provider.summarize(
        build_theme_prompt(lead + notable), system=THEME_SYSTEM_PROMPT, max_tokens=120
    )
    if theme_res is not None:
        theme = _clean(theme_res[0]).strip('"').strip()
        if theme:
            payload["theme"] = theme
            model_used = theme_res[1]

    body_res = provider.summarize(
        build_editorial_prompt(lead, notable, in_brief),
        system=EDITORIAL_SYSTEM_PROMPT,
        max_tokens=1000,
    )
    if body_res is not None:
        payload.update(_parse_body(body_res[0]))
        model_used = body_res[1]

    # Useful only if at least a theme or some per-pick copy came back.
    if "theme" not in payload and not payload.get("picks"):
        return None
    return payload, model_used
