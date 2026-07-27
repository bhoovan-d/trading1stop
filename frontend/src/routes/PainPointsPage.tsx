import { useDemandSignals } from "../api/client";
import type { DemandSignal } from "../types";

/** Ranked by how many separate traders raised it — the count IS the signal. */
function MentionChip({ count }: { count: number }) {
  return (
    <div className="flex w-14 shrink-0 flex-col items-center rounded-md bg-surface-2 px-2 py-2 text-center">
      <span className="font-mono text-xl font-semibold leading-none tabular-nums text-accent">
        {count}
      </span>
      <span className="mt-1 font-mono text-[10px] uppercase leading-tight tracking-wide text-faint">
        asked
      </span>
    </div>
  );
}

function SignalCard({ signal, index }: { signal: DemandSignal; index: number }) {
  return (
    <article
      className="rounded-lg border border-border bg-surface p-5 shadow-[var(--shadow-sm)]"
      style={{ animation: "rise 0.4s var(--ease-out-quint) both", animationDelay: `${Math.min(index, 12) * 28}ms` }}
    >
      <div className="flex gap-4">
        <MentionChip count={signal.mention_count} />

        <div className="min-w-0 flex-1">
          {signal.region === "India" && (
            <span className="mb-2 inline-block rounded-sm bg-surface-2 px-1.5 py-0.5 font-mono text-[10px] uppercase tracking-wide text-muted">
              India
            </span>
          )}
          <h3
            className="font-serif text-xl font-semibold leading-snug text-ink [overflow-wrap:anywhere]"
            style={{ fontVariationSettings: '"opsz" 34' }}
          >
            “{signal.question}”
          </h3>

          {signal.summary && (
            <p className="mt-2 text-sm leading-relaxed text-muted">{signal.summary}</p>
          )}

          {signal.opportunity && (
            <p className="mt-3 text-sm leading-relaxed text-ink">
              <span className="mr-2 font-mono text-[11px] uppercase tracking-wide text-accent">
                The gap
              </span>
              {signal.opportunity}
            </p>
          )}

          {signal.evidence.length > 0 && (
            <details className="mt-3 group">
              <summary className="cursor-pointer font-mono text-[11px] uppercase tracking-wide text-faint hover:text-muted">
                {signal.evidence.length} thread{signal.evidence.length === 1 ? "" : "s"}
              </summary>
              <ul className="mt-2 space-y-1.5 border-l border-border pl-3">
                {signal.evidence.map((e) => (
                  <li key={e.url}>
                    <a
                      href={e.url}
                      target="_blank"
                      rel="noreferrer"
                      className="text-sm leading-snug text-muted underline-offset-2 hover:text-ink hover:underline"
                    >
                      {e.title}
                    </a>
                  </li>
                ))}
              </ul>
            </details>
          )}
        </div>
      </div>
    </article>
  );
}

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
