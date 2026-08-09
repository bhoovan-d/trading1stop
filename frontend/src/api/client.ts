import {
  keepPreviousData,
  useInfiniteQuery,
  useMutation,
  useQuery,
  useQueryClient,
} from "@tanstack/react-query";
import type {
  AdminRun,
  AdminStatus,
  DemandSignal,
  InsightPage,
  Meta,
  NewsletterList,
  NewsletterOut,
  RunMode,
} from "../types";

async function getJSON<T>(url: string): Promise<T> {
  const res = await fetch(url);
  if (!res.ok) {
    throw new Error(`Request failed (${res.status})`);
  }
  return res.json() as Promise<T>;
}

export interface Filters {
  category?: string;
  approach?: string;
  item_type?: string;
  exclude_item_type?: string;
  region?: string;
  timeframe?: string;
  market_index?: string;
  min_score?: number;
  source?: string;
  stream?: "alpha" | "community";
  date_from?: string;
  date_to?: string;
  q?: string;
  sort?: "score" | "date";
  page?: number;
  page_size?: number;
}

function toQuery(filters: Filters): string {
  const params = new URLSearchParams();
  for (const [key, value] of Object.entries(filters)) {
    if (value !== undefined && value !== null && value !== "") {
      params.set(key, String(value));
    }
  }
  return params.toString();
}

export function useInsights(filters: Filters) {
  const qs = toQuery(filters);
  return useQuery({
    queryKey: ["insights", qs],
    queryFn: () => getJSON<InsightPage>(`/api/insights?${qs}`),
    placeholderData: keepPreviousData,
  });
}

/** How many insights load at a time. The feed shows this many up front and keeps the rest behind
 *  "Load more" — the API caps page_size at 100, so more than this needs a second request anyway. */
export const BATCH_SIZE = 100;

/** Paginated feed that APPENDS rather than replacing, for the load-more UX. */
export function useInfiniteInsights(filters: Filters) {
  const qs = toQuery({ ...filters, page: undefined, page_size: BATCH_SIZE });
  return useInfiniteQuery({
    queryKey: ["insights-infinite", qs],
    initialPageParam: 1,
    queryFn: ({ pageParam }) => getJSON<InsightPage>(`/api/insights?${qs}&page=${pageParam}`),
    getNextPageParam: (last) =>
      last.page * last.page_size < last.total ? last.page + 1 : undefined,
    placeholderData: keepPreviousData,
  });
}

export function useMeta() {
  return useQuery({ queryKey: ["meta"], queryFn: () => getJSON<Meta>("/api/meta") });
}

export function useNewsletters() {
  return useQuery({
    queryKey: ["newsletters"],
    queryFn: () => getJSON<NewsletterList>("/api/newsletters"),
  });
}

export function useNewsletter(date?: string) {
  return useQuery({
    queryKey: ["newsletter", date],
    queryFn: () => getJSON<NewsletterOut>(`/api/newsletters/${date}`),
    enabled: Boolean(date),
  });
}

export function useDemandSignals(kind: "demand" | "firm" = "demand") {
  return useQuery({
    queryKey: ["demand-signals", kind],
    queryFn: () => getJSON<DemandSignal[]>(`/api/demand-signals?kind=${kind}`),
  });
}

// ── Admin ─────────────────────────────────────────────────────────────────────
// Every /api/admin/* route is gated server-side on this token; it travels as a header, never in a
// URL or query string, so it can't leak into logs, referrers, or browser history.

export const ADMIN_TOKEN_KEY = "alpha-admin-token";

export class AdminAuthError extends Error {}

async function adminFetch<T>(path: string, token: string, init?: RequestInit): Promise<T> {
  const res = await fetch(path, {
    ...init,
    headers: {
      ...(init?.headers ?? {}),
      "Content-Type": "application/json",
      "X-Admin-Token": token,
    },
  });
  if (res.status === 401 || res.status === 503) {
    // 401 = wrong token, 503 = ADMIN_TOKEN unset on the server. Both mean "you can't get in",
    // and both must send the UI back to the locked state rather than showing a broken panel.
    const body = await res.json().catch(() => null);
    throw new AdminAuthError(body?.detail ?? "Unauthorized");
  }
  if (!res.ok) {
    const body = await res.json().catch(() => null);
    throw new Error(body?.detail ?? `Request failed (${res.status})`);
  }
  return res.json() as Promise<T>;
}

export function useAdminStatus(token: string) {
  return useQuery({
    queryKey: ["admin-status", token],
    queryFn: () => adminFetch<AdminStatus>("/api/admin/status", token),
    enabled: Boolean(token),
    retry: false, // a bad token should surface immediately, not after three attempts
  });
}

/** Statuses GitHub reports for a run that hasn't finished yet. */
const RUN_IN_FLIGHT = new Set(["queued", "in_progress", "requested", "waiting", "pending"]);

export function useAdminRuns(token: string) {
  return useQuery({
    queryKey: ["admin-runs", token],
    queryFn: () => adminFetch<AdminRun[]>("/api/admin/runs", token),
    enabled: Boolean(token),
    retry: false,
    // Poll only while a run is actually in flight, so an idle console sits quiet. The function
    // form reads the query's own latest data, which keeps this to a single query.
    refetchInterval: (query) =>
      (query.state.data ?? []).some((r) => RUN_IN_FLIGHT.has(r.status ?? "")) ? 10_000 : false,
  });
}

export function useRunPipeline(token: string) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (vars: { mode: RunMode; sources: string }) =>
      adminFetch<{ dispatched: boolean }>("/api/admin/run", token, {
        method: "POST",
        body: JSON.stringify(vars),
      }),
    onSuccess: () => {
      // GitHub takes a moment to register the run, so the immediate refetch may miss it; the
      // poll in useAdminRuns picks it up.
      queryClient.invalidateQueries({ queryKey: ["admin-runs", token] });
    },
  });
}
