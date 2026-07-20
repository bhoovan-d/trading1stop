import { useEffect, useState, type ReactNode } from "react";
import type { Meta } from "../types";
import { categoryColor, sourceLabel } from "../lib";
import { Popover } from "./Popover";

export interface FilterValues {
  category: string;
  approach: string;
  min_score: string;
  source: string;
  date_from: string;
  date_to: string;
  q: string;
  sort: string;
}

interface Props {
  values: FilterValues;
  meta?: Meta;
  active: boolean;
  onChange: (key: keyof FilterValues, value: string) => void;
  onApplyMany: (patch: Partial<FilterValues>) => void;
  onClear: () => void;
  // Hide the category facet row when the view is locked to a single category (e.g. Quant Firms tab).
  hideCategories?: boolean;
}

// ── Timeframe presets (replace native date pickers) ────────────────────────────
const DAY_MS = 86_400_000;
const TIMEFRAMES = [
  { value: "all", label: "All", days: 0 },
  { value: "24h", label: "24h", days: 1 },
  { value: "7d", label: "7d", days: 7 },
  { value: "30d", label: "30d", days: 30 },
];

function isoDaysAgo(days: number): string {
  return new Date(Date.now() - days * DAY_MS).toISOString().slice(0, 10);
}

/** Which preset the current `date_from` corresponds to ("" = a custom/unmatched value). */
function activeTimeframe(dateFrom: string): string {
  if (!dateFrom) return "all";
  for (const t of TIMEFRAMES) if (t.days > 0 && isoDaysAgo(t.days) === dateFrom) return t.value;
  return "";
}

// ── Shared controls ────────────────────────────────────────────────────────────
function Pill({
  label,
  selected,
  color,
  onClick,
}: {
  label: string;
  selected: boolean;
  color?: string;
  onClick: () => void;
}) {
  const accent = color ?? "var(--color-accent-dim)";
  return (
    <button
      type="button"
      onClick={onClick}
      aria-pressed={selected}
      className={`rounded-full border px-3 py-1 text-xs font-medium transition-colors duration-150 ${
        selected ? "" : "border-border bg-surface text-muted hover:border-border-strong hover:text-ink"
      }`}
      style={
        selected
          ? {
              color: accent,
              backgroundColor: `color-mix(in oklab, ${accent} 12%, var(--color-surface))`,
              borderColor: `color-mix(in oklab, ${accent} 40%, transparent)`,
            }
          : undefined
      }
    >
      {label}
    </button>
  );
}

function Segmented({
  options,
  value,
  onChange,
  ariaLabel,
}: {
  options: { value: string; label: string }[];
  value: string;
  onChange: (v: string) => void;
  ariaLabel: string;
}) {
  return (
    <div
      role="group"
      aria-label={ariaLabel}
      className="inline-flex items-center rounded-md border border-border bg-surface p-0.5 shadow-[var(--shadow-sm)]"
    >
      {options.map((o) => {
        const on = o.value === value;
        return (
          <button
            key={o.value || "any"}
            type="button"
            aria-pressed={on}
            onClick={() => onChange(o.value)}
            className={`rounded-[7px] px-2.5 py-1 text-xs font-medium tabular-nums transition-colors duration-150 ${
              on ? "bg-accent-tint text-accent-dim" : "text-muted hover:text-ink"
            }`}
          >
            {o.label}
          </button>
        );
      })}
    </div>
  );
}

function Field({ label, children }: { label: string; children: ReactNode }) {
  return (
    <div className="flex flex-col gap-1.5">
      <span className="text-[11px] font-medium text-faint">{label}</span>
      {children}
    </div>
  );
}

// ── Icons ────────────────────────────────────────────────────────────────────
const iconProps = {
  viewBox: "0 0 24 24",
  fill: "none",
  stroke: "currentColor",
  strokeWidth: 2,
  strokeLinecap: "round" as const,
  strokeLinejoin: "round" as const,
};

// ── FilterBar ──────────────────────────────────────────────────────────────────
const SCORE_OPTS = [
  { value: "", label: "Any" },
  { value: "7", label: "7+" },
  { value: "8", label: "8+" },
  { value: "9", label: "9+" },
  { value: "10", label: "10" },
];

export function FilterBar({ values, meta, active, onChange, onApplyMany, onClear, hideCategories }: Props) {
  const [q, setQ] = useState(values.q);

  // keep local search in sync when cleared/navigated externally
  useEffect(() => setQ(values.q), [values.q]);

  // debounce the search field into the URL/query
  useEffect(() => {
    const id = setTimeout(() => {
      if (q !== values.q) onChange("q", q);
    }, 300);
    return () => clearTimeout(id);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [q]);

  const categories = meta?.categories ?? [];
  const approaches = meta?.approaches ?? [];
  const sources = meta?.sources ?? [];
  const activeCount = [values.min_score, values.approach, values.source, values.date_from].filter(
    Boolean,
  ).length;

  function setTimeframe(v: string) {
    if (v === "all") return onApplyMany({ date_from: "", date_to: "" });
    const t = TIMEFRAMES.find((x) => x.value === v);
    if (t) onApplyMany({ date_from: isoDaysAgo(t.days), date_to: "" });
  }

  return (
    <div className="sticky top-0 z-10 -mx-4 border-b border-border bg-bg/85 px-4 py-3.5 backdrop-blur-md">
      {/* search · filters · sort */}
      <div className="flex items-center gap-2">
        <div className="relative flex-1">
          <svg className="pointer-events-none absolute left-3.5 top-1/2 h-4 w-4 -translate-y-1/2 text-faint" {...iconProps}>
            <circle cx="11" cy="11" r="7" />
            <path d="m21 21-4.3-4.3" />
          </svg>
          <input
            value={q}
            onChange={(e) => setQ(e.target.value)}
            placeholder="Search summaries, impact, titles…"
            aria-label="Search insights"
            className="w-full rounded-lg border border-border bg-surface py-2.5 pl-10 pr-9 text-sm text-ink shadow-[var(--shadow-sm)] outline-none transition-colors placeholder:text-faint focus:border-accent-dim"
          />
          {q && (
            <button
              type="button"
              onClick={() => setQ("")}
              aria-label="Clear search"
              className="absolute right-2 top-1/2 grid h-6 w-6 -translate-y-1/2 place-items-center rounded-full text-faint transition-colors hover:bg-surface-2 hover:text-ink"
            >
              <svg className="h-3.5 w-3.5" {...iconProps}>
                <path d="M18 6 6 18M6 6l12 12" />
              </svg>
            </button>
          )}
        </div>

        <Popover
          label="Filters"
          align="end"
          width={300}
          trigger={({ ref, onClick, "aria-expanded": expanded, "aria-haspopup": haspopup, "data-open": dataOpen }) => (
            <button
              ref={ref}
              type="button"
              onClick={onClick}
              aria-expanded={expanded}
              aria-haspopup={haspopup}
              aria-label={activeCount ? `Filters, ${activeCount} active` : "Filters"}
              data-open={dataOpen}
              className="group inline-flex shrink-0 items-center gap-1.5 rounded-lg border border-border bg-surface px-3 py-2.5 text-xs font-medium text-muted shadow-[var(--shadow-sm)] transition-colors hover:border-border-strong hover:text-ink data-[open=true]:border-accent-dim data-[open=true]:text-accent-dim"
            >
              <svg className="h-4 w-4" {...iconProps}>
                <path d="M3 5h18M6 12h12M10 19h4" />
              </svg>
              <span className="hidden sm:inline">Filters</span>
              {activeCount > 0 && (
                <span className="grid h-4 min-w-4 place-items-center rounded-full bg-accent-tint px-1 font-mono text-[10px] font-semibold tabular-nums text-accent-dim">
                  {activeCount}
                </span>
              )}
              <svg className="h-3.5 w-3.5 text-faint transition-transform duration-150 group-data-[open=true]:rotate-180" {...iconProps}>
                <path d="m6 9 6 6 6-6" />
              </svg>
            </button>
          )}
        >
          {() => (
            <div className="flex flex-col gap-4">
              <Field label="Minimum score">
                <Segmented
                  ariaLabel="Minimum score"
                  options={SCORE_OPTS}
                  value={values.min_score}
                  onChange={(v) => onChange("min_score", v)}
                />
              </Field>

              {approaches.length > 0 && (
                <Field label="Approach">
                  <div className="flex flex-wrap gap-1.5">
                    <Pill label="All" selected={values.approach === ""} onClick={() => onChange("approach", "")} />
                    {approaches.map((a) => (
                      <Pill
                        key={a}
                        label={a}
                        selected={values.approach === a}
                        onClick={() => onChange("approach", values.approach === a ? "" : a)}
                      />
                    ))}
                  </div>
                </Field>
              )}

              <Field label="Source">
                <div className="flex flex-wrap gap-1.5">
                  <Pill label="All" selected={values.source === ""} onClick={() => onChange("source", "")} />
                  {sources.map((s) => (
                    <Pill
                      key={s}
                      label={sourceLabel(s)}
                      selected={values.source === s}
                      onClick={() => onChange("source", values.source === s ? "" : s)}
                    />
                  ))}
                </div>
              </Field>

              <Field label="When">
                <Segmented
                  ariaLabel="Timeframe"
                  options={TIMEFRAMES.map((t) => ({ value: t.value, label: t.label }))}
                  value={activeTimeframe(values.date_from)}
                  onChange={setTimeframe}
                />
              </Field>

              {active && (
                <button
                  type="button"
                  onClick={onClear}
                  className="self-start text-xs font-medium text-faint underline-offset-4 transition-colors hover:text-ink hover:underline"
                >
                  Clear all filters
                </button>
              )}
            </div>
          )}
        </Popover>

        <Segmented
          ariaLabel="Sort order"
          options={[
            { value: "score", label: "Top" },
            { value: "date", label: "Newest" },
          ]}
          value={values.sort || "score"}
          onChange={(v) => onChange("sort", v)}
        />
      </div>

      {/* category facets */}
      {!hideCategories && (
        <div className="mt-3 flex flex-wrap items-center gap-1.5">
          <Pill label="All" selected={values.category === ""} onClick={() => onChange("category", "")} />
          {categories.map((c) => (
            <Pill
              key={c}
              label={c}
              color={categoryColor(c)}
              selected={values.category === c}
              onClick={() => onChange("category", values.category === c ? "" : c)}
            />
          ))}
        </div>
      )}
    </div>
  );
}
