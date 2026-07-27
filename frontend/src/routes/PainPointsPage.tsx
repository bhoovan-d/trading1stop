import { useDemandSignals } from "../api/client";
import { SignalCard } from "../components/SignalCard";

export function PainPointsPage() {
  const { data, isLoading, isError } = useDemandSignals();

  return (
    <div>
      <div className="mb-5 mt-6">
        <h1
          className="font-serif text-2xl font-semibold tracking-tight text-ink"
          style={{ fontVariationSettings: '"opsz" 40' }}
        >
          What Traders Want
        </h1>
        <p className="mt-1.5 max-w-2xl text-sm leading-relaxed text-muted">
          The same questions, asked over and over across r/algotrading, r/options and the Indian
          trading subs. One person asking is noise; a dozen asking is an unmet need — and every
          signal here links back to the threads behind it.
        </p>
      </div>

      {isLoading ? (
        <div className="space-y-3">
          {Array.from({ length: 4 }).map((_, i) => (
            <div
              key={i}
              className="h-36 animate-pulse rounded-lg border border-border bg-surface shadow-[var(--shadow-sm)]"
            />
          ))}
        </div>
      ) : isError ? (
        <EmptyState
          title="Couldn't load demand signals"
          body="Is the API running? Start it with: uv run alpha-engine serve"
        />
      ) : !data || data.length === 0 ? (
        <EmptyState
          title="No recurring signals yet"
          body="Run: uv run alpha-engine demand-signals"
        />
      ) : (
        <div className="space-y-3">
          {data.map((s, i) => (
            <SignalCard key={s.id} signal={s} index={i} />
          ))}
        </div>
      )}
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
