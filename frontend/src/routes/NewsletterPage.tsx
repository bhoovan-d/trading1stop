import { NavLink, useParams } from "react-router-dom";
import { useNewsletter, useNewsletters } from "../api/client";
import { Markdown } from "../components/Markdown";
import { formatDate } from "../lib";

export function NewsletterPage() {
  const { date } = useParams();
  const { data: list } = useNewsletters();
  const dates = list?.dates ?? [];
  const selected = date ?? dates[0];
  const { data, isLoading } = useNewsletter(selected);

  return (
    <div className="mt-8">
      {dates.length > 0 && (
        <div className="mb-6 flex flex-wrap gap-1.5">
          {dates.map((d) => (
            <NavLink
              key={d}
              to={`/newsletter/${d}`}
              className={() =>
                `rounded-full border px-3 py-1 font-mono text-xs transition-colors ${
                  d === selected
                    ? "border-transparent bg-accent-tint text-accent-dim"
                    : "border-border bg-surface text-muted hover:border-border-strong hover:text-ink"
                }`
              }
            >
              {formatDate(d)}
            </NavLink>
          ))}
        </div>
      )}

      {!selected ? (
        <div className="rounded-lg border border-dashed border-border-strong bg-surface px-6 py-16 text-center shadow-[var(--shadow-sm)]">
          <p className="font-serif text-lg font-semibold text-ink" style={{ fontVariationSettings: '"opsz" 32' }}>
            No newsletters yet
          </p>
          <p className="mt-1.5 font-mono text-xs text-faint">
            Generate one with: uv run alpha-engine gen-newsletter
          </p>
        </div>
      ) : isLoading ? (
        <div className="h-64 animate-pulse rounded-lg border border-border bg-surface shadow-[var(--shadow-md)]" />
      ) : data ? (
        <div className="rounded-lg border border-border bg-surface px-6 py-8 shadow-[var(--shadow-md)] sm:px-10 sm:py-10">
          <Markdown source={data.markdown} />
        </div>
      ) : null}
    </div>
  );
}
