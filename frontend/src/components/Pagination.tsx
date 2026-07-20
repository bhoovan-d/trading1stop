interface Props {
  page: number;
  pageSize: number;
  total: number;
  onPage: (page: number) => void;
}

export function Pagination({ page, pageSize, total, onPage }: Props) {
  const pages = Math.max(1, Math.ceil(total / pageSize));
  if (total === 0) return null;
  const start = (page - 1) * pageSize + 1;
  const end = Math.min(page * pageSize, total);

  const btn =
    "rounded-md border border-border bg-surface px-3 py-1.5 font-mono text-xs text-muted shadow-[var(--shadow-sm)] transition-colors enabled:hover:border-border-strong enabled:hover:text-ink disabled:cursor-not-allowed disabled:opacity-40 disabled:shadow-none";

  return (
    <div className="mt-8 flex items-center justify-between">
      <span className="font-mono text-xs text-faint">
        {start}–{end} of {total}
      </span>
      <div className="flex items-center gap-2">
        <button className={btn} disabled={page <= 1} onClick={() => onPage(page - 1)}>
          ← Prev
        </button>
        <span className="font-mono text-xs text-muted">
          {page} / {pages}
        </span>
        <button className={btn} disabled={page >= pages} onClick={() => onPage(page + 1)}>
          Next →
        </button>
      </div>
    </div>
  );
}
