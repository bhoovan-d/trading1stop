import { NavLink, Outlet } from "react-router-dom";
import { useMeta } from "../api/client";

function NavItem({ to, label, end }: { to: string; label: string; end?: boolean }) {
  return (
    <NavLink
      to={to}
      end={end}
      className={({ isActive }) =>
        `rounded-md px-3 py-1.5 text-sm font-medium transition-colors ${
          isActive ? "bg-accent-tint text-accent-dim" : "text-muted hover:text-ink"
        }`
      }
    >
      {label}
    </NavLink>
  );
}

export function Layout() {
  const { data: meta } = useMeta();

  return (
    <div className="min-h-full">
      <header className="border-b border-border bg-surface">
        <div className="mx-auto flex max-w-4xl flex-wrap items-center gap-x-4 gap-y-2 px-4 py-3.5">
          <div className="flex shrink-0 items-center gap-3">
            <span
              className="grid h-10 w-10 place-items-center rounded-lg font-serif text-xl font-semibold shadow-[var(--shadow-sm)]"
              style={{
                color: "var(--color-accent-ink)",
                backgroundColor: "var(--color-accent)",
              }}
            >
              α
            </span>
            <div className="leading-tight">
              <div
                className="whitespace-nowrap font-serif text-[17px] font-semibold tracking-tight text-ink"
                style={{ fontVariationSettings: '"opsz" 36' }}
              >
                Trading Alpha Engine
              </div>
              <div className="mt-0.5 text-xs text-faint">Your morning read on AI &amp; ML in trading</div>
            </div>
          </div>

          <nav className="ml-auto flex items-center gap-1">
            <NavItem to="/" label="Feed" end />
            <NavItem to="/launches" label="Launches" />
            <NavItem to="/jobs" label="Jobs" />
            <NavItem to="/quant-firms" label="Quant Firms" />
            <NavItem to="/india" label="India" />
            <NavItem to="/community" label="Community" />
            <NavItem to="/newsletter" label="Newsletter" />
          </nav>

          {meta && (
            <div className="hidden items-baseline gap-1.5 border-l border-border pl-4 sm:flex">
              <span className="font-mono text-sm font-semibold tabular-nums text-accent-dim">
                {meta.total_insights}
              </span>
              <span className="text-xs text-faint">insights</span>
            </div>
          )}
        </div>
      </header>

      <main className="mx-auto max-w-4xl px-4 pb-24">
        <Outlet />
      </main>
    </div>
  );
}
