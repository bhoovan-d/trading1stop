import { keepPreviousData, useInfiniteQuery, useQuery } from "@tanstack/react-query";
import type { DemandSignal, InsightPage, Meta, NewsletterList, NewsletterOut } from "../types";

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
