import type { DemandSignal } from "../types";

/** The two signal kinds share a shape but not a vocabulary: a demand signal is something people
 *  ASKED, a firm signal is a count of ROLES. Using one wording for both reads plainly wrong. */
const COPY = {
  demand: { unit: "asked", evidence: "thread", lead: "The gap", quoted: true },
  firm: { unit: "roles", evidence: "posting", lead: "What it means", quoted: false },
} as const;

function labelsFor(kind: string) {
  return kind === "firm" ? COPY.firm : COPY.demand;
}

/** Ranked by how much evidence backs it — the count IS the signal. */
function MentionChip({ count, unit }: { count: number; unit: string }) {
  return (
    <div className="flex w-14 shrink-0 flex-col items-center rounded-md bg-surface-2 px-2 py-2 text-center">
      <span className="font-mono text-xl font-semibold leading-none tabular-nums text-accent">
        {count}
      </span>
      <span className="mt-1 font-mono text-[10px] uppercase leading-tight tracking-wide text-faint">
        {unit}
      </span>
    </div>
  );
}

export function SignalCard({ signal, index }: { signal: DemandSignal; index: number }) {
  const copy = labelsFor(signal.kind);
  return (
    <article
      className="rounded-lg border border-border bg-surface p-5 shadow-[var(--shadow-sm)]"
      style={{ animation: "rise 0.4s var(--ease-out-quint) both", animationDelay: `${Math.min(index, 12) * 28}ms` }}
    >
      <div className="flex gap-4">
        <MentionChip count={signal.mention_count} unit={copy.unit} />

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
            {copy.quoted ? `“${signal.question}”` : signal.question}
          </h3>

          {signal.summary && (
            <p className="mt-2 text-sm leading-relaxed text-muted">{signal.summary}</p>
          )}

          {signal.opportunity && (
            <p className="mt-3 text-sm leading-relaxed text-ink">
              <span className="mr-2 font-mono text-[11px] uppercase tracking-wide text-accent">
                {copy.lead}
              </span>
              {signal.opportunity}
            </p>
          )}

          {signal.evidence.length > 0 && (
            <details className="mt-3 group">
              <summary className="cursor-pointer font-mono text-[11px] uppercase tracking-wide text-faint hover:text-muted">
                {signal.evidence.length} {copy.evidence}
                {signal.evidence.length === 1 ? "" : "s"}
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

