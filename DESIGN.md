---
name: Trading Alpha Engine
description: A warm, premium morning read on how AI & ML are reshaping trading.
colors:
  bg: "oklch(0.985 0.006 70)"
  surface: "oklch(1 0 0)"
  surface-2: "oklch(0.965 0.008 70)"
  border: "oklch(0.9 0.008 70)"
  border-strong: "oklch(0.83 0.01 70)"
  ink: "oklch(0.26 0.012 60)"
  muted: "oklch(0.44 0.012 60)"
  faint: "oklch(0.52 0.012 60)"
  accent: "oklch(0.64 0.17 35)"
  accent-ink: "oklch(0.99 0.005 70)"
  accent-dim: "oklch(0.5 0.15 34)"
  accent-tint: "oklch(0.93 0.03 40)"
  cat-agentic: "oklch(0.52 0.13 300)"
  cat-ml: "oklch(0.52 0.1 235)"
  cat-risk: "oklch(0.48 0.13 8)"
  cat-infra: "oklch(0.56 0.09 75)"
typography:
  display:
    fontFamily: "Fraunces Variable, Fraunces, Georgia, serif"
    fontSize: "1.875rem"
    fontWeight: 600
    lineHeight: 1.1
    letterSpacing: "-0.02em"
  headline:
    fontFamily: "Fraunces Variable, Fraunces, Georgia, serif"
    fontSize: "1.5rem"
    fontWeight: 600
    lineHeight: 1.15
    letterSpacing: "-0.02em"
  title:
    fontFamily: "Fraunces Variable, Fraunces, Georgia, serif"
    fontSize: "1.125rem"
    fontWeight: 600
    lineHeight: 1.35
    letterSpacing: "normal"
  reading:
    fontFamily: "Fraunces Variable, Fraunces, Georgia, serif"
    fontSize: "1.0625rem"
    fontWeight: 400
    lineHeight: 1.7
    letterSpacing: "normal"
  body:
    fontFamily: "Inter Variable, Inter, ui-sans-serif, system-ui, sans-serif"
    fontSize: "0.875rem"
    fontWeight: 400
    lineHeight: 1.6
    letterSpacing: "normal"
  data:
    fontFamily: "ui-monospace, SF Mono, JetBrains Mono, Menlo, monospace"
    fontSize: "0.6875rem"
    fontWeight: 500
    lineHeight: 1.3
    letterSpacing: "normal"
  label:
    fontFamily: "Inter Variable, Inter, ui-sans-serif, system-ui, sans-serif"
    fontSize: "0.625rem"
    fontWeight: 600
    lineHeight: 1.2
    letterSpacing: "0.1em"
rounded:
  sm: "8px"
  md: "10px"
  lg: "14px"
  full: "9999px"
spacing:
  xs: "6px"
  sm: "10px"
  md: "16px"
  lg: "20px"
  xl: "40px"
components:
  button-nav:
    textColor: "{colors.muted}"
    typography: "{typography.body}"
    rounded: "{rounded.md}"
    padding: "6px 12px"
  button-nav-active:
    backgroundColor: "{colors.accent-tint}"
    textColor: "{colors.accent-dim}"
    rounded: "{rounded.md}"
    padding: "6px 12px"
  pill:
    textColor: "{colors.muted}"
    backgroundColor: "{colors.surface}"
    typography: "{typography.body}"
    rounded: "{rounded.full}"
    padding: "4px 12px"
  pill-selected:
    backgroundColor: "{colors.accent-tint}"
    textColor: "{colors.accent-dim}"
    rounded: "{rounded.full}"
    padding: "4px 12px"
  input-search:
    backgroundColor: "{colors.surface}"
    textColor: "{colors.ink}"
    rounded: "{rounded.md}"
    padding: "8px 12px 8px 36px"
  card-insight:
    backgroundColor: "{colors.surface}"
    textColor: "{colors.ink}"
    rounded: "{rounded.lg}"
    padding: "20px"
  card-reading:
    backgroundColor: "{colors.surface}"
    textColor: "{colors.ink}"
    rounded: "{rounded.lg}"
    padding: "40px"
  button-page:
    backgroundColor: "{colors.surface}"
    textColor: "{colors.muted}"
    typography: "{typography.data}"
    rounded: "{rounded.md}"
    padding: "6px 12px"
---

# Design System: Trading Alpha Engine

## 1. Overview

**Creative North Star: "First Light"**

Trading Alpha Engine is the calm, premium thing you open with your morning coffee — a
well-made daily broadsheet on how AI and ML are reshaping the trading process, not a
blinking terminal. The surface is barely-warm off-white paper; content sits on pure-white
cards that lift on soft, warm shadows; a single friendly poppy-coral accent carries the
warmth and marks what's live. Headlines and long-form reading are set in Fraunces, a warm
serif with real optical-size personality; the working UI — labels, nav, summaries — is
Inter; anything the machine measured (scores, dates, sources, counts) stays in tabular
mono. The whole system should feel positive, unhurried, and trustworthy at 7am.

Warmth here is deliberate and *earned by the accent and the type*, never by a saturated
body background. The paper is a true low-chroma off-white (OKLCH chroma ≈ 0.006), not a
cream/beige/parchment tint — that warm-neutral band is the saturated default of AI-generated
2026 and reading as generic is the one thing this redesign exists to escape. The coral, the
serif, and the soft shadows do the warming; the background stays quiet.

This system explicitly rejects: the dark "quant terminal" it replaced (charcoal + neon
green + mono-everything); the SaaS-cream editorial cliché (warm-tinted body + terracotta +
tiny tracked eyebrows on every section); gradient hero metrics; and decorative
glassmorphism. It is confident, warm, and legible before it is clever.

**Key Characteristics:**
- Barely-warm off-white paper (`bg`, OKLCH L0.985 C0.006); pure-white cards above it.
- Depth from **soft warm shadows**, not borders-as-decoration or flat tonal steps.
- One poppy-coral accent, used sparingly — active nav, links, high scores, the brand mark.
- Fraunces serif for display + reading; Inter for UI; tabular mono for data.
- A six-hue category index (by trading style), muted for a light surface, plus neutral tech sub-tags.
- Fixed rem type scale (no `clamp()`); comfortable reading measures (≤68–70ch).

## 2. Colors

A warm, low-chroma neutral field (hue ~60–70) with one saturated poppy-coral accent and a
muted six-hue category index. Restrained by default; the coral earns its rarity.

### Primary
- **Poppy Coral** (`oklch(0.64 0.17 35)`): the accent voice — the brand `α` tile, and any
  bright accent fill/border. Friendly and warm, used sparingly. Too light for text on white
  (~3:1), so text/links use the deep variant below.
- **Deep Coral** (`oklch(0.5 0.15 34)`): the readable accent — links, the "Why it matters"
  kicker, active-nav text, focus-ring borders, newsletter section labels. ~6.5:1 on white.
- **Coral Tint** (`oklch(0.93 0.03 40)`): soft selected/active fills — active nav pill,
  selected filter pills, date chips. Pairs with Deep Coral text.
- **Warm White** (`oklch(0.99 0.005 70)`): text/glyph *on* a coral fill (the `α` mark).

### Secondary — The Category Index
Six muted hues (all ~L0.50) that classify insights by **trading style**, readable as text on
their own tint and distinct on a light surface. A functional index, not decoration.
- **Slate Blue** (`oklch(0.52 0.1 235)`): *Technical Analysis*.
- **Ochre** (`oklch(0.56 0.09 75)`): *Macro Analysis*.
- **Warm Red** (`oklch(0.5 0.14 20)`): *Intraday Trading* — kept distinct from the coral accent
  so the two never read as the same thing.
- **Muted Plum** (`oklch(0.52 0.13 300)`): *Swing Trading*.
- **Green** (`oklch(0.5 0.1 150)`): *Fundamental Analysis*.
- **Slate Teal** (`oklch(0.52 0.08 200)`): *Quant Firms*.

The 8-band **score** fill uses its own token (`--color-score-mid`, the ochre value) so it stays
independent of any category hue. The **tech approach** sub-tags (Agentic AI, Machine Learning,
Automation, Sentiment & News, Infrastructure & Data, Risk & Sizing) are intentionally *neutral*
mono chips — they annotate without competing with the category hue.

### Neutral — Warm Paper Ramp
- **Paper** (`oklch(0.985 0.006 70)`): the page background. Barely warm, never cream.
- **White** (`oklch(1 0 0)`): cards, inputs, reading surface, header.
- **Fill** (`oklch(0.965 0.008 70)`): faint raised fill for form controls.
- **Border** (`oklch(0.9 0.008 70)`) / **Border Strong** (`oklch(0.83 0.01 70)`): hairlines
  and stronger dividers/hover outlines.
- **Ink** (`oklch(0.26 0.012 60)`): headlines, titles, primary text (~15.5:1 on white).
- **Muted** (`oklch(0.44 0.012 60)`): body prose, summaries (~7.8:1).
- **Faint** (`oklch(0.52 0.012 60)`): metadata, timestamps, placeholders (~5.6:1 — kept
  dark enough for small text; do not lighten).

### Named Rules
**The One Voice Rule.** Coral appears on ≤10% of any screen — the brand mark, the current
selection, links, and the strongest scores. Its rarity is what makes a live signal read as
live. Never use coral as decoration or on inactive states.

**The Earned-Warmth Rule.** Warmth comes from the accent, the serif, and the shadows —
never from tinting the body background toward cream. The paper stays at chroma ≈ 0.006. If
the background starts to read as beige/sand/parchment, the chroma is too high: pull it back.

**The Two-Reds Rule.** The Deep Berry risk hue and the Poppy Coral accent must stay
visibly distinct — berry is darker and cooler (hue 8 vs 35). Never let a risk chip drift
toward the accent's brightness.

## 3. Typography

**Display / Reading Font:** Fraunces Variable (warm serif; with Georgia fallback)
**UI / Body Font:** Inter Variable (humanist sans; with system-ui fallback)
**Data Font:** system monospace stack

**Character:** A contrast-axis pairing — a warm, high-personality serif against a neutral,
highly legible sans, split by *role*, not decoration. Fraunces carries the things you read
for pleasure and orientation (page titles, insight titles, the newsletter body); Inter
carries the working UI (summaries, nav, labels, controls); mono carries measured data
(scores, dates, sources, counts). Fraunces's optical-size (`opsz`) axis is used
deliberately — higher `opsz` on large display headings for that crisp, high-contrast
broadsheet feel; lower on smaller serif.

### Hierarchy
- **Display** (Fraunces 600, `1.875rem`/30px, `opsz` 64, line-height 1.1): the newsletter
  masthead H1 and the **"The Alpha Feed"** feed masthead — the largest type in the app.
- **Headline** (Fraunces 600, `1.5rem`/24px, `opsz` 40): page titles (Community heading).
- **Title** (Fraunces 600, `1.25rem`/20px, `opsz` 34): insight card titles and newsletter
  item titles — sized up from 18px so the thing you read leads the card.
- **Reading** (Fraunces 400, `1.0625rem`/17px, line-height 1.7, ≤68ch): the newsletter
  body — a proper long-form reading measure in ink at ~90% for comfort.
- **Body** (Inter 400, `0.875rem`/14px, line-height 1.6, `muted`, ≤68ch): card summaries
  and trader-impact text.
- **Data** (mono 500, `0.6875rem`/11px, `faint`): source labels, dates, pagination counts,
  category tags. The **score number is the loudest data in the app** — mono **700 at
  `1.6rem`/~26px, tabular** (the score is the product; it leads the card); its `/ 10`
  denominator sits below at 9px `faint`.
- **Label** (Inter 600, `0.625rem`–`0.6875rem`/10–11px, tracking 0.1em, UPPERCASE): the
  "Why it matters" kicker, newsletter section labels, filter micro-labels.

### Named Rules
**The Read-in-Serif Rule.** Long-form newsletter prose is set in Fraunces at 17px/1.7 — it
is meant to be *read*, and the serif makes a morning read feel considered. UI micro-copy
and card summaries stay in Inter; don't set working UI in the serif.

**The Fixed-Scale Rule.** No `clamp()`, no fluid headings. Sizes are a fixed rem ramp so a
title in a narrow card and one in a wide column read at the same weight.

## 4. Elevation

This is a light system, so depth is carried by **soft, warm shadows** — a real elevation
model, unlike the dark predecessor's flat tonal steps. Shadows are tinted with the ink hue
at low alpha (never neutral gray, never black) so they read as warm morning light, not
grime. Cards rest on a medium shadow and lift on hover; the reading surface sits on the same
medium shadow; small controls (search, pagination, date chips) carry only the faintest
shadow to separate them from the paper.

### Shadow Vocabulary
- **`--shadow-sm`** (`0 1px 2px …/0.05, 0 1px 3px …/0.05`): inputs, pagination, the brand
  tile — a hairline of lift.
- **`--shadow-md`** (`0 2px 4px …/0.05, 0 6px 16px …/0.07`): insight cards and the
  newsletter reading surface at rest.
- **`--shadow-lg`** (`0 12px 32px …/0.10, 0 3px 8px …/0.06`): card hover and any popover —
  paired with a 2px upward translate.

### Named Rules
**The Warm-Shadow Rule.** All shadows are tinted with the ink hue (`oklch(0.26 0.012 60)`)
at low alpha, never neutral black. A cool/black shadow on warm paper looks like dirt; the
warm tint reads as light.

**The Lift-on-Intent Rule.** Cards rest on `--shadow-md`; hover raises to `--shadow-lg` +
`-translate-y-0.5`. Motion is on shadow and transform only — never on layout.

## 5. Components

### Buttons & Nav
- **Nav:** Inter medium, sentence case (not tracked uppercase). Inactive = `muted`, hover
  `ink`; active = `accent-tint` fill + `accent-dim` text, `md` radius. The header is white
  with a hairline bottom border and scrolls with the page.
- **Segmented Control:** the shared toggle for small mutually-exclusive sets (sort Top/Newest,
  minimum score, timeframe presets). A hairline-bordered `md`-radius container on `--shadow-sm`
  with a 2px inset; the active segment is a coral-tint inset pill (`accent-tint` fill +
  `accent-dim` text), inactive segments `muted` → `ink` on hover. This is the vocabulary that
  replaced the native `<select>` and date inputs — the toolbar carries no OS chrome.
- **Pagination:** white with a hairline border and `--shadow-sm`; `muted` text → `ink` and
  `border-strong` on hover; disabled at 40% opacity, shadow removed.

### Overlays
- **Filters Popover:** progressive disclosure for the feed's secondary filters. A **"Filters"**
  button (with an `accent-tint` count badge for active score/source/timeframe filters) opens a
  white card (`lg` radius, `--shadow-lg`) of segmented + pill controls. **Portaled to `<body>`**
  so the sticky bar's `backdrop-blur` can't clip it; anchored below-right of the trigger and
  clamped to the viewport (`max-width: min(320px, 100vw − 24px)`). Esc / outside-click dismiss,
  focus returns to the trigger; a `rise` entrance that the reduced-motion rule disables.

### Chips & Pills
- **Filter Pill:** full-radius. Unselected = white + `border` + `muted` text. Selected =
  a 12%-tint fill of its color over white + a 40% border + the deep readable hue as text
  (Deep Coral for accent pills, the category hue for category pills).
- **Category Tag:** mono 11px uppercase, full radius, a 13% tint fill of the category hue
  over white with a 36% border, text in the full hue (~5.7:1 on its tint).

### Cards / Containers
- **Insight Card (signature):** white, `lg` radius (14px), hairline `border`, 20px padding,
  `--shadow-md` at rest → `--shadow-lg` + lift on hover (keeps the staggered `rise`
  entrance). Left column: a **56×56 Score Chip** — a category/score-tinted rounded square,
  the number in the hue mixed 72% toward ink for contrast (≥4.3:1 as large text) over `N / 10`.
  **Fill scales with the score** so the strongest signal wears the strongest fill: 9-10 =
  22% tint / 52% border, 8 = 16% / 42%, ≤7 = 12% / 34%. Right column: metadata row, a
  **serif** linked title (hover → Deep Coral + underline), an Inter summary, and an impact
  line led by the Deep Coral "Why it matters" kicker.
- **Reading Surface (newsletter):** white card, `lg` radius, `--shadow-md`, 40px padding —
  a premium letter. Serif masthead, Deep Coral section labels, serif reading body.
- **Empty State:** white, dashed `border-strong`, `--shadow-sm`, a serif title and a mono
  hint (often the CLI command to run). Teaches the next step, never just "nothing here."
- **Skeleton:** white card-height blocks with `--shadow-sm`, `animate-pulse`. Loading shows
  skeletons, never a centered spinner.

### Inputs / Fields
- **Search / Select / Date:** white (search) or `Fill` (selects/dates) with a `border`,
  `md` radius, `[color-scheme:light]` so native pickers render light. Search carries an
  inline `faint` magnifier and a 300ms debounce. Focus shifts the border to `accent-dim`
  (a color change, not a glow). Placeholders sit at `faint`.

## 6. Do's and Don'ts

### Do:
- **Do** keep the body background a true low-chroma off-white (`oklch(0.985 0.006 70)`) and
  carry warmth through the coral accent, the Fraunces serif, and warm shadows.
- **Do** keep coral under the 10%-of-screen ceiling — brand mark, current selection, links,
  high scores. Use **Deep Coral** (`accent-dim`) for anything that is text on white.
- **Do** set long-form newsletter reading in Fraunces (17px/1.7, ≤68ch) and working UI /
  card summaries in Inter; keep scores, dates, sources, counts in tabular mono.
- **Do** build depth with the soft warm shadow scale (`sm`/`md`/`lg`), lifting cards on
  hover with `--shadow-lg` + a 2px translate.
- **Do** tint category chips as a light fill of their hue over white with the hue as text;
  keep each hue mapped to one category everywhere.
- **Do** keep muted/faint text dark enough to pass AA (muted ≥7:1, faint ≥5:1 on white);
  if a value drifts light, pull it toward ink.

### Don't:
- **Don't** tint the body background toward cream / beige / sand / parchment. That warm-
  neutral band is the saturated AI-generated default of 2026; it is the exact look this
  redesign exists to escape. Warmth lives in the accent + type, not the paper.
- **Don't** use neutral-gray or black shadows on the warm paper — they read as grime. All
  shadows are tinted with the ink hue at low alpha.
- **Don't** let the Deep Berry risk hue and the Poppy Coral accent read as the same red;
  keep berry darker and cooler.
- **Don't** set working UI, nav, labels, or data in the serif — Fraunces is for display and
  long-form reading only; Inter and mono carry the rest.
- **Don't** use gradient text, gradient hero metrics, or a big-number/small-label SaaS
  metric template.
- **Don't** use glassmorphism decoratively, or tiny tracked uppercase eyebrows above every
  section — the newsletter's Deep Coral section labels are content structure, not scaffold.
- **Don't** use `border-left`/`border-right` colored stripes as accents; use full borders,
  tint fills, the score chip, or nothing.
- **Don't** revert to the dark charcoal + neon-green terminal, or reintroduce a dark theme
  without an explicit, toggled opt-in.
