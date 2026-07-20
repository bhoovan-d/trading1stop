import { useSearchParams } from "react-router-dom";
import { useInsights, useMeta } from "../api/client";
import { FilterBar, type FilterValues } from "../components/FilterBar";
import { InsightCard } from "../components/InsightCard";
import { Pagination } from "../components/Pagination";

const PAGE_SIZE = 20;
const FILTER_KEYS = ["category", "approach", "min_score", "source", "date_from", "date_to", "q"] as const;

export function FeedPage({
  stream,
  lockedCategory,
}: { stream?: "alpha" | "community"; lockedCategory?: string } = {}) {
  const [params, setParams] = useSearchParams();
  const { data: meta } = useMeta();
  const isCommunity = stream === "community";
  const isFirms = lockedCategory != null;

  const values: FilterValues = {
    category: params.get("category") ?? "",
    approach: params.get("approach") ?? "",
    min_score: params.get("min_score") ?? "",
    source: params.get("source") ?? "",
    date_from: params.get("date_from") ?? "",
    date_to: params.get("date_to") ?? "",
    q: params.get("q") ?? "",
    sort: params.get("sort") ?? "score",
  };
  const page = Math.max(1, Number(params.get("page") ?? "1"));
  const active = FILTER_KEYS.some((k) => values[k] !== "");

  function setFilter(key: keyof FilterValues, value: string) {
    const next = new URLSearchParams(params);
    if (value) next.set(key, value);
    else next.delete(key);
    if (key !== "sort") next.delete("page"); // any filter change returns to page 1
    setParams(next, { replace: true });
  }

  // Apply several filter keys in one URL update (sequential setFilter calls would clobber each
  // other via a stale `params`). Used by the timeframe presets (set date_from + clear date_to).
  function applyFilters(patch: Partial<FilterValues>) {
    const next = new URLSearchParams(params);
    let touchedNonSort = false;
    for (const [key, value] of Object.entries(patch)) {
      if (value) next.set(key, value);
      else next.delete(key);
      if (key !== "sort") touchedNonSort = true;
    }
    if (touchedNonSort) next.delete("page");
    setParams(next, { replace: true });
  }

  function setPage(p: number) {
    const next = new URLSearchParams(params);
    if (p <= 1) next.delete("page");
    else next.set("page", String(p));
    setParams(next);
    window.scrollTo({ top: 0, behavior: "smooth" });
  }

  function clearAll() {
    const next = new URLSearchParams();
    if (values.sort && values.sort !== "score") next.set("sort", values.sort);
    setParams(next, { replace: true });
  }

  const { data, isLoading, isError, isPlaceholderData } = useInsights({
    category: lockedCategory ?? (values.category || undefined),
    approach: values.approach || undefined,
    min_score: values.min_score ? Number(values.min_score) : undefined,
    source: values.source || undefined,
    stream,
    date_from: values.date_from || undefined,
    date_to: values.date_to || undefined,
    q: values.q || undefined,
    sort: values.sort as "score" | "date",
    page,
    page_size: PAGE_SIZE,
  });

  return (
    <div>
      {isFirms ? (
        <div className="mb-5 mt-6">
          <h1
            className="font-serif text-2xl font-semibold tracking-tight text-ink"
            style={{ fontVariationSettings: '"opsz" 40' }}
          >
            Quant Firms
          </h1>
          <p className="mt-1.5 max-w-2xl text-sm leading-relaxed text-muted">
            What leading quant &amp; HFT firms — Jane Street, Jump, DRW, IMC, Tower Research and peers —
            are building and hiring for. Scored job postings and firm engineering signals reveal where
            the institutional edge is heading, so you can watch it from the outside.
          </p>
        </div>
      ) : isCommunity ? (
        <div className="mb-5 mt-6">
          <h1
            className="font-serif text-2xl font-semibold tracking-tight text-ink"
            style={{ fontVariationSettings: '"opsz" 40' }}
          >
            Community Discussions
          </h1>
          <p className="mt-1.5 max-w-2xl text-sm leading-relaxed text-muted">
            Practical strategy engineering, tooling, and infrastructure chatter from r/algotrading,
            r/quant, r/quantconnect, and the QuantConnect forum — held to a lighter relevance bar than
            the main alpha feed.
          </p>
        </div>
      ) : (
        <header className="mb-6 mt-6">
          <div className="flex flex-wrap items-end justify-between gap-x-6 gap-y-1.5">
            <h1
              className="font-serif text-3xl font-semibold tracking-tight text-balance text-ink"
              style={{ fontVariationSettings: '"opsz" 64' }}
            >
              The Alpha Feed
            </h1>
            {data && (
              <span className="font-mono text-[11px] uppercase tracking-wide tabular-nums text-faint">
                {data.total.toLocaleString()} {active ? "matching" : "insights"}
              </span>
            )}
          </div>
          <p className="mt-2 max-w-2xl text-sm leading-relaxed text-muted">
            Every update is read and scored by the engine, then framed with why it matters — so your
            morning goes to the alpha, not the noise.
          </p>
        </header>
      )}

      <FilterBar
        values={values}
        meta={meta}
        active={active}
        onChange={setFilter}
        onApplyMany={applyFilters}
        onClear={clearAll}
        hideCategories={isFirms}
      />

      <div className="mt-5">
        {isLoading ? (
          <SkeletonList />
        ) : isError ? (
          <EmptyState
            title="Couldn't load insights"
            body="Is the API running? Start it with: uv run alpha-engine serve"
          />
        ) : !data || data.items.length === 0 ? (
          <EmptyState
            title="No insights match"
            body={
              active
                ? "Try loosening the filters."
                : isFirms
                  ? "No quant-firm signals yet — they'll appear after the next pipeline run."
                  : isCommunity
                    ? "No community discussions yet — they'll appear after the next pipeline run."
                    : "Run the pipeline to populate the feed."
            }
          />
        ) : (
          <div
            className={`space-y-3 transition-opacity duration-200 ${isPlaceholderData ? "opacity-60" : "opacity-100"}`}
          >
            {data.items.map((insight, i) => (
              <InsightCard key={insight.id} insight={insight} index={i} />
            ))}
          </div>
        )}

        {data && (
          <Pagination page={page} pageSize={PAGE_SIZE} total={data.total} onPage={setPage} />
        )}
      </div>
    </div>
  );
}

function SkeletonList() {
  return (
    <div className="space-y-3">
      {Array.from({ length: 5 }).map((_, i) => (
        <div
          key={i}
          className="h-32 animate-pulse rounded-lg border border-border bg-surface shadow-[var(--shadow-sm)]"
        />
      ))}
    </div>
  );
}

function EmptyState({ title, body }: { title: string; body: string }) {
  return (
    <div className="rounded-lg border border-dashed border-border-strong bg-surface px-6 py-16 text-center shadow-[var(--shadow-sm)]">
      <p className="font-serif text-lg font-semibold text-ink" style={{ fontVariationSettings: '"opsz" 32' }}>
        {title}
      </p>
      <p className="mt-1.5 font-mono text-xs text-faint">{body}</p>
    </div>
  );
}
