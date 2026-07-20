import type { Insight } from "../types";
import { categoryColor, formatDate, isBadgeItemType, itemTypeLabel, scoreColor, sourceLabel } from "../lib";

function ItemTypeBadge({ itemType }: { itemType: string }) {
  // Launch / Funding / Early Stage news wear the accent so product signals stand out.
  return (
    <span
      className="rounded-full px-2 py-0.5 font-mono text-[10px] font-semibold uppercase tracking-wide"
      style={{
        color: "var(--color-accent-dim)",
        backgroundColor: "var(--color-accent-tint)",
        border: "1px solid color-mix(in oklab, var(--color-accent) 30%, transparent)",
      }}
    >
      {itemTypeLabel(itemType)}
    </span>
  );
}

function RegionBadge() {
  return (
    <span className="rounded-full border border-border bg-surface-2 px-2 py-0.5 font-mono text-[10px] font-semibold tracking-wide text-muted">
      🇮🇳 India
    </span>
  );
}

function CategoryTag({ category }: { category: string }) {
  const color = categoryColor(category);
  return (
    <span
      className="rounded-full px-2.5 py-0.5 font-mono text-[11px] font-medium uppercase tracking-wide"
      style={{
        color,
        backgroundColor: `color-mix(in oklab, ${color} 13%, var(--color-surface))`,
        border: `1px solid color-mix(in oklab, ${color} 36%, transparent)`,
      }}
    >
      {category}
    </span>
  );
}

function ApproachTag({ label }: { label: string }) {
  // Secondary axis (tech). Neutral styling so the trading-style category stays the lead.
  return (
    <span className="rounded-full border border-border bg-surface-2 px-2 py-0.5 font-mono text-[10px] font-medium tracking-wide text-muted">
      {label}
    </span>
  );
}

function ScoreChip({ score }: { score: number }) {
  const color = scoreColor(score);
  const ink = `color-mix(in oklab, ${color} 72%, var(--color-ink))`;
  // Weight tied to meaning: the strongest signals wear the strongest fill, so a 9-10 reads
  // as unmistakably more important than a 7 without changing the layout.
  const fill = score >= 9 ? 22 : score >= 8 ? 16 : 12;
  const stroke = score >= 9 ? 52 : score >= 8 ? 42 : 34;
  return (
    <div
      className="flex h-14 w-14 shrink-0 flex-col items-center justify-center rounded-lg font-mono leading-none"
      style={{
        color: ink,
        backgroundColor: `color-mix(in oklab, ${color} ${fill}%, var(--color-surface))`,
        border: `1px solid color-mix(in oklab, ${color} ${stroke}%, transparent)`,
      }}
      title={`Relevance ${score}/10`}
    >
      <span className="text-[1.6rem] font-bold tabular-nums tracking-tight">{score}</span>
      <span className="mt-0.5 text-[9px] font-medium text-faint">/ 10</span>
    </div>
  );
}

export function InsightCard({ insight, index }: { insight: Insight; index: number }) {
  return (
    <article
      className="group rounded-lg border border-border bg-surface p-5 shadow-[var(--shadow-md)] transition-[box-shadow,transform,border-color] duration-200 ease-[var(--ease-out-quint)] hover:-translate-y-0.5 hover:border-border-strong hover:shadow-[var(--shadow-lg)]"
      style={{ animation: "rise 0.4s var(--ease-out-quint) both", animationDelay: `${Math.min(index, 12) * 28}ms` }}
    >
      <div className="flex gap-4">
        <ScoreChip score={insight.relevance_score} />

        <div className="min-w-0 flex-1">
          <div className="mb-2 flex flex-wrap items-center gap-x-3 gap-y-1.5">
            <CategoryTag category={insight.category} />
            {isBadgeItemType(insight.item_type) && <ItemTypeBadge itemType={insight.item_type} />}
            {insight.region === "India" && <RegionBadge />}
            {insight.approaches?.map((a) => (
              <ApproachTag key={a} label={a} />
            ))}
            {insight.workflow_stage && <ApproachTag label={insight.workflow_stage} />}
            <span className="font-mono text-[11px] uppercase tracking-wide text-faint">
              {sourceLabel(insight.source)}
            </span>
            {insight.item_created_at && (
              <span className="font-mono text-[11px] text-faint">· {formatDate(insight.item_created_at)}</span>
            )}
          </div>

          <h3
            className="font-serif text-xl font-semibold leading-snug text-ink [overflow-wrap:anywhere]"
            style={{ fontVariationSettings: '"opsz" 34' }}
          >
            <a
              href={insight.url}
              target="_blank"
              rel="noreferrer"
              className="underline-offset-4 transition-colors hover:text-accent-dim hover:underline"
            >
              {insight.title}
            </a>
          </h3>

          <p className="mt-2 max-w-[68ch] text-[14px] leading-relaxed text-muted">{insight.technical_summary}</p>

          <p className="mt-3 max-w-[68ch] text-[13.5px] leading-relaxed text-muted">
            <span className="mr-1.5 text-[10px] font-semibold uppercase tracking-wider text-accent-dim">
              Why it matters
            </span>
            {insight.trader_impact}
          </p>
        </div>
      </div>
    </article>
  );
}
