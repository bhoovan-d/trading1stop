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
from typing import TYPE_CHECKING

from ..intelligence.provider import CascadeProvider
from ..models import Insight, RawItem

if TYPE_CHECKING:
    from .generate import Sections

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
You are the editor of a daily intelligence brief on how AI is helping people trade. Your readers \
are ACTIVE TRADERS — technical, algo, macro, and desk traders — technically literate but NOT ML \
researchers. Your voice is calm, editorial, and curated: you explain, you never hype or market.

You are writing copy to SELL this brief to everyday traders, so PLAIN LANGUAGE is the rule. Turn \
dense notes into clear editorial copy: for every pick, explain in plain words WHAT it is and WHY a \
trader should care — the capability, edge, or risk it changes. No unexplained jargon; if a concept \
matters, gloss it in a few plain words (never bare terms like "H^2_T" or "square-integrable \
processes"). Lead with meaning, not mechanism. A non-expert must get each line in ONE read.

You will receive today's picks, each with an id, a section (launch | strategy | india | \
watch_list | hiring), and its raw notes. Return STRICT JSON and nothing else — no markdown fences, \
no prose around it — in exactly this shape:
{
  "editor_note": "<2-3 sentences of narrative synthesis>",
  "picks": {
    "<id>": {"summary": "<editorial copy for that pick>"}
  },
  "worth_trying": {
    "<id>": {"why": "<1 sentence: why a trader should actually test this now>"}
  }
}

EDITOR'S NOTE rules: 2-3 sentences naming the SPECIFIC threads across today's picks and why they \
matter now. BANNED filler: "significant developments", "gain a more nuanced understanding", "make \
more informed decisions", "competitive edge", "stay ahead", "leveraging these". Write what a \
knowledgeable editor would actually say.

WORTH TRYING: choose 1-3 pick ids a trader could realistically install, sign up for, or try THIS \
WEEK — favour shipped launches and ready-to-use tools over research. One plain sentence each on why.

Length per section: launch summary = 2-3 informative sentences; strategy / india summary = 1 \
sentence; watch_list summary = 1 short clause (under ~20 words) with a skeptical, not-yet-proven \
framing; hiring summary = 1 short clause naming the role/desk and what it signals the firm is \
building. Include every pick id you are given in "picks". Do not restate the title. No commentary \
outside the JSON.
"""


def build_theme_prompt(picks: list[Row]) -> str:
    lines = ["Today's headline picks:", ""]
    for insight, raw in picks:
        lines.append(f"- [{insight.category}] {raw.title}")
        lines.append(f"  Why it matters: {insight.trader_impact.strip()}")
    lines.append("")
    lines.append("Write the single-sentence theme.")
    return "\n".join(lines)


def _pick_lines(insight: Insight, raw: RawItem, section: str) -> list[str]:
    lines = [
        f"- id: {insight.id}",
        f"  section: {section}",
        f"  category: {insight.category}",
        f"  item_type: {getattr(insight, 'item_type', 'tooling')}",
        f"  region: {getattr(insight, 'region', 'Global')}",
    ]
    stage = getattr(insight, "workflow_stage", None)
    if stage:
        lines.append(f"  workflow_stage: {stage}")
    lines += [
        f"  title: {raw.title}",
        f"  technical_notes: {insight.technical_summary.strip()}",
        f"  trader_impact: {insight.trader_impact.strip()}",
    ]
    return lines


def _sectioned_picks(sec: "Sections") -> list[tuple[str, Row]]:
    """Every selected row paired with its section label, de-duplicated (launch/watch/india/strategy)."""
    seen: set[int] = set()
    out: list[tuple[str, Row]] = []
    groups = [
        ("launch", sec.launches),
        ("watch_list", sec.watch_list),
        ("hiring", sec.hiring),
        ("india", sec.india),
        ("strategy", [r for rows in sec.strategy.values() for r in rows] + sec.quant_firms),
    ]
    for label, rows in groups:
        for row in rows:
            if id(row) not in seen:
                seen.add(id(row))
                out.append((label, row))
    return out


def build_editorial_prompt(sec: "Sections") -> str:
    lines = ["Today's picks:", ""]
    for label, (insight, raw) in _sectioned_picks(sec):
        lines += _pick_lines(insight, raw, label)
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
    worth: dict[str, dict] = {}
    worth_in = data.get("worth_trying")
    if isinstance(worth_in, dict):
        for key, val in worth_in.items():
            why = val.get("why") if isinstance(val, dict) else val
            if isinstance(why, str) and why.strip():
                worth[str(key)] = {"why": _clean(why)}
    if worth:
        out["worth_trying"] = worth
    return out


def generate_editorial(
    sec: "Sections",
    provider: CascadeProvider,
) -> tuple[dict, str] | None:
    """Return (payload, model_used) for the day's picks, or None if unavailable/all failed.

    Two calls: a focused theme call (sharper headlines) and one editorial call for the note,
    per-pick copy, and Worth-Trying picks. Each degrades independently; a payload is returned if
    either succeeds. The payload carries ``version: 2``.
    """
    all_rows = [row for _, row in _sectioned_picks(sec)]
    if not all_rows or not provider.available:
        return None

    payload: dict = {"version": 2, "picks": {}}
    model_used = ""

    # Lead the theme call with the flagship sections (launches + India), else fall back to all.
    theme_rows = sec.launches + sec.india or all_rows
    theme_res = provider.summarize(
        build_theme_prompt(theme_rows), system=THEME_SYSTEM_PROMPT, max_tokens=120
    )
    if theme_res is not None:
        theme = _clean(theme_res[0]).strip('"').strip()
        if theme:
            payload["theme"] = theme
            model_used = theme_res[1]

    body_res = provider.summarize(
        build_editorial_prompt(sec),
        system=EDITORIAL_SYSTEM_PROMPT,
        max_tokens=1100,
    )
    if body_res is not None:
        payload.update(_parse_body(body_res[0]))
        model_used = body_res[1]

    # Useful only if at least a theme or some per-pick copy came back.
    if "theme" not in payload and not payload.get("picks"):
        return None
    return payload, model_used
