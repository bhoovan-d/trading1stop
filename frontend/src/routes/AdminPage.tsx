import { useEffect, useState } from "react";
import {
  ADMIN_TOKEN_KEY,
  AdminAuthError,
  useAdminRuns,
  useAdminStatus,
  useRunPipeline,
} from "../api/client";
import type { AdminRun, AdminStatus, RunMode } from "../types";
import { formatDate } from "../lib";

/** Kept in sync with RUN_MODES in src/alpha_engine/api/admin.py and daily.yml's `mode` choices. */
const MODES: { value: RunMode; label: string; blurb: string }[] = [
  { value: "full", label: "Full run", blurb: "Ingest, score, prune, then rebuild the newsletter." },
  { value: "ingest", label: "Ingest only", blurb: "Fetch new raw items. No LLM calls, no spend." },
  { value: "synthesize", label: "Synthesize", blurb: "Score whatever is sitting unprocessed." },
  {
    value: "rescore",
    label: "Re-score site",
    blurb:
      "Re-score 100 posts already on the site under the current prompt, oldest first. Curation is " +
      "kept — unlike Reclassify, nothing you pruned comes back. Run it repeatedly to work through.",
  },
  { value: "newsletter", label: "Newsletter", blurb: "Regenerate today's brief from the database." },
  {
    value: "reclassify",
    label: "Reclassify all",
    blurb:
      "Wipe every insight and re-score the ENTIRE archive, including posts pruned from the site — " +
      "they will come back. Use Re-score site instead unless you want the full corpus rebuilt.",
  },
];

const RUNNING = new Set(["queued", "in_progress", "requested", "waiting", "pending"]);

export function AdminPage() {
  const [token, setToken] = useState(() => localStorage.getItem(ADMIN_TOKEN_KEY) ?? "");

  const status = useAdminStatus(token);
  const locked = !token || status.error instanceof AdminAuthError;

  // Clear a token the server has rejected, so a stale secret doesn't sit in storage forever.
  useEffect(() => {
    if (status.error instanceof AdminAuthError) localStorage.removeItem(ADMIN_TOKEN_KEY);
  }, [status.error]);

  if (locked) {
    return (
      <Unlock
        error={status.error instanceof AdminAuthError ? status.error.message : null}
        onSubmit={(value) => {
          localStorage.setItem(ADMIN_TOKEN_KEY, value);
          setToken(value);
        }}
      />
    );
  }

  return (
    <Console
      token={token}
      status={status.data}
      loading={status.isLoading}
      statusError={status.error as Error | null}
      onSignOut={() => {
        localStorage.removeItem(ADMIN_TOKEN_KEY);
        setToken("");
      }}
    />
  );
}

// ── Locked state ──────────────────────────────────────────────────────────────

function Unlock({ error, onSubmit }: { error: string | null; onSubmit: (v: string) => void }) {
  const [value, setValue] = useState("");

  return (
    <div className="mx-auto mt-24 max-w-sm">
      <h1
        className="font-serif text-2xl font-semibold tracking-tight text-ink"
        style={{ fontVariationSettings: '"opsz" 40' }}
      >
        Admin
      </h1>
      <p className="mt-1.5 text-sm leading-relaxed text-muted">
        Enter the admin token to run the pipeline.
      </p>

      <form
        className="mt-5"
        onSubmit={(e) => {
          e.preventDefault();
          if (value.trim()) onSubmit(value.trim());
        }}
      >
        <input
          type="password"
          autoFocus
          value={value}
          onChange={(e) => setValue(e.target.value)}
          placeholder="Admin token"
          aria-label="Admin token"
          className="w-full rounded-md border border-border bg-surface px-3 py-2 font-mono text-sm text-ink shadow-[var(--shadow-sm)] outline-none placeholder:text-faint focus:border-accent"
        />
        {error && <p className="mt-2 text-xs text-accent">{error}</p>}
        <button
          type="submit"
          disabled={!value.trim()}
          className="mt-3 w-full rounded-md bg-ink px-3 py-2 text-sm font-medium text-bg transition-opacity hover:opacity-90 disabled:opacity-40"
        >
          Unlock
        </button>
      </form>
    </div>
  );
}

// ── Unlocked state ────────────────────────────────────────────────────────────

function Console({
  token,
  status,
  loading,
  statusError,
  onSignOut,
}: {
  token: string;
  status?: AdminStatus;
  loading: boolean;
  statusError: Error | null;
  onSignOut: () => void;
}) {
  const [mode, setMode] = useState<RunMode>("full");
  const [sources, setSources] = useState("");
  const [confirm, setConfirm] = useState("");

  const run = useRunPipeline(token);
  const runs = useAdminRuns(token); // self-polls while a run is in flight

  const destructive = mode === "reclassify";
  const blocked = destructive && confirm.trim().toUpperCase() !== "RECLASSIFY";

  return (
    <div className="mt-6">
      <div className="flex items-baseline justify-between gap-4">
        <div>
          <h1
            className="font-serif text-2xl font-semibold tracking-tight text-ink"
            style={{ fontVariationSettings: '"opsz" 40' }}
          >
            Admin
          </h1>
          <p className="mt-1.5 max-w-2xl text-sm leading-relaxed text-muted">
            Runs happen on GitHub Actions, not here — the pipeline takes minutes and needs the LLM
            and ingestion libraries the web function doesn't carry. This dispatches that workflow
            and reports back.
          </p>
        </div>
        <button
          onClick={onSignOut}
          className="shrink-0 font-mono text-xs uppercase tracking-wide text-faint transition-colors hover:text-ink"
        >
          Sign out
        </button>
      </div>

      <Panel title="Status">
        {loading ? (
          <div className="h-16 animate-pulse rounded-md bg-bg" />
        ) : !status ? (
          // Without this the panel rendered an empty box when the query failed, which looks
          // identical to "still loading" and tells you nothing.
          <p className="text-xs text-accent">
            {statusError?.message ?? "Couldn't load status."}
          </p>
        ) : (
          <>
            <div className="grid grid-cols-2 gap-4 sm:grid-cols-4">
              <Stat label="Insights" value={status.total_insights.toLocaleString()} />
              <Stat
                label="Awaiting scoring"
                value={status.unprocessed_raw_items.toLocaleString()}
                hint={status.unprocessed_raw_items > 0 ? "a run is due" : undefined}
              />
              <Stat label="Raw items" value={status.total_raw_items.toLocaleString()} />
              <Stat label="Latest brief" value={status.latest_newsletter ?? "—"} />
            </div>
            <p className="mt-4 font-mono text-xs text-faint">
              Newest insight: {formatDate(status.latest_insight_at) || "none yet"}
              {" · "}
              {status.source_count} source{status.source_count === 1 ? "" : "s"} tracked
            </p>
            {!status.dispatch_configured && (
              <p className="mt-3 rounded-md border border-dashed border-border-strong px-3 py-2 text-xs text-accent">
                Workflow dispatch isn't configured. Set <code>GITHUB_REPO</code> and{" "}
                <code>GITHUB_DISPATCH_TOKEN</code> in the deployment environment to enable runs.
              </p>
            )}
          </>
        )}
      </Panel>

      <Panel title="Run pipeline">
        <div className="flex flex-wrap gap-1.5">
          {MODES.map((m) => (
            <button
              key={m.value}
              onClick={() => {
                setMode(m.value);
                setConfirm("");
              }}
              className="rounded-full border px-3 py-1 text-xs transition-colors"
              style={{
                borderColor: mode === m.value ? "var(--color-accent)" : "var(--color-border)",
                color: mode === m.value ? "var(--color-accent)" : "var(--color-muted)",
                background: mode === m.value ? "var(--color-accent-tint)" : "transparent",
              }}
            >
              {m.label}
            </button>
          ))}
        </div>
        <p className="mt-2.5 text-xs leading-relaxed text-muted">
          {MODES.find((m) => m.value === mode)?.blurb}
        </p>

        {(mode === "full" || mode === "ingest") && (
          <input
            value={sources}
            onChange={(e) => setSources(e.target.value)}
            placeholder="Sources (optional) — e.g. github,reddit"
            aria-label="Sources"
            className="mt-3 w-full rounded-md border border-border bg-surface px-3 py-2 font-mono text-xs text-ink outline-none placeholder:text-faint focus:border-accent"
          />
        )}

        {destructive && (
          <div className="mt-3">
            <p className="text-xs leading-relaxed text-accent">
              This deletes every insight and the newsletter archive, then re-scores the entire corpus
              from stored raw content. Type RECLASSIFY to confirm.
            </p>
            <input
              value={confirm}
              onChange={(e) => setConfirm(e.target.value)}
              placeholder="RECLASSIFY"
              aria-label="Type RECLASSIFY to confirm"
              className="mt-2 w-full rounded-md border border-border bg-surface px-3 py-2 font-mono text-xs text-ink outline-none placeholder:text-faint focus:border-accent"
            />
          </div>
        )}

        <button
          onClick={() => {
            run.mutate({ mode, sources });
            setConfirm("");
          }}
          disabled={run.isPending || blocked || !status?.dispatch_configured}
          className="mt-4 rounded-md bg-ink px-4 py-2 text-sm font-medium text-bg transition-opacity hover:opacity-90 disabled:opacity-40"
        >
          {run.isPending ? "Dispatching…" : "Run now"}
        </button>

        {run.isSuccess && (
          <span className="ml-3 text-xs text-muted">
            Dispatched. It takes a few seconds to appear below.
          </span>
        )}
        {run.isError && (
          <span className="ml-3 text-xs text-accent">{(run.error as Error).message}</span>
        )}
      </Panel>

      <Panel title="Recent runs">
        {runs.isLoading ? (
          <div className="h-12 animate-pulse rounded-md bg-bg" />
        ) : runs.isError ? (
          <p className="text-xs text-muted">{(runs.error as Error).message}</p>
        ) : !runs.data?.length ? (
          <p className="text-xs text-muted">No runs yet.</p>
        ) : (
          <ul className="divide-y divide-border">
            {runs.data.map((r) => (
              <RunRow key={r.id} run={r} />
            ))}
          </ul>
        )}
      </Panel>
    </div>
  );
}

// ── Pieces ────────────────────────────────────────────────────────────────────

function Panel({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <section className="mt-5 rounded-lg border border-border bg-surface p-5 shadow-[var(--shadow-sm)]">
      <h2 className="mb-3.5 font-mono text-xs uppercase tracking-wide text-faint">{title}</h2>
      {children}
    </section>
  );
}

function Stat({ label, value, hint }: { label: string; value: string; hint?: string }) {
  return (
    <div>
      <div className="font-mono text-xl text-ink">{value}</div>
      <div className="mt-0.5 text-xs text-muted">{label}</div>
      {hint && <div className="mt-0.5 text-xs text-accent">{hint}</div>}
    </div>
  );
}

function RunRow({ run }: { run: AdminRun }) {
  const running = RUNNING.has(run.status ?? "");
  const ok = run.conclusion === "success";
  const color = running
    ? "var(--color-score-mid)"
    : ok
      ? "var(--color-muted)"
      : "var(--color-accent)";
  const state = running ? (run.status ?? "running") : (run.conclusion ?? "—");

  return (
    <li className="flex items-center justify-between gap-4 py-2.5">
      <div className="min-w-0">
        <div className="truncate text-sm text-ink">{run.display_title ?? run.name ?? "Run"}</div>
        <div className="mt-0.5 font-mono text-xs text-faint">
          {run.created_at ? new Date(run.created_at).toLocaleString() : ""}
        </div>
      </div>
      <div className="flex shrink-0 items-center gap-3">
        <span className="font-mono text-xs uppercase tracking-wide" style={{ color }}>
          {state}
        </span>
        {run.html_url && (
          <a
            href={run.html_url}
            target="_blank"
            rel="noreferrer"
            className="font-mono text-xs text-faint underline-offset-2 hover:text-ink hover:underline"
          >
            logs
          </a>
        )}
      </div>
    </li>
  );
}
