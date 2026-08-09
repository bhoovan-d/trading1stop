export interface Insight {
  id: number;
  relevance_score: number;
  category: string;
  approaches: string[];
  item_type: string;
  region: string;
  workflow_stage?: string | null;
  timeframe?: string | null;
  market_index?: string | null;
  technical_summary: string;
  trader_impact: string;
  model_used: string;
  created_at: string;
  source: string;
  stream: "alpha" | "community";
  title: string;
  url: string;
  author?: string | null;
  item_created_at?: string | null;
}

export interface InsightPage {
  items: Insight[];
  total: number;
  page: number;
  page_size: number;
}

export interface Meta {
  categories: string[];
  approaches: string[];
  item_types: string[];
  regions: string[];
  timeframes: string[];
  market_indexes: string[];
  sources: string[];
  score_min: number;
  score_max: number;
  date_min: string | null;
  date_max: string | null;
  total_insights: number;
  alpha_count: number;
  community_count: number;
}

export interface NewsletterList {
  dates: string[];
}

export interface NewsletterOut {
  date: string;
  markdown: string;
}

export interface DemandEvidence {
  title: string;
  url: string;
}

export interface DemandSignal {
  id: number;
  kind: string;
  question: string;
  summary: string;
  opportunity: string;
  mention_count: number;
  region: string;
  evidence: DemandEvidence[];
  created_at: string;
}

// ── Admin ─────────────────────────────────────────────────────────────────────
// Must match RUN_MODES in src/alpha_engine/api/admin.py and the `mode` choices in daily.yml.
export type RunMode = "full" | "ingest" | "synthesize" | "newsletter" | "reclassify";

export interface AdminStatus {
  total_insights: number;
  latest_insight_at: string | null;
  total_raw_items: number;
  unprocessed_raw_items: number;
  latest_newsletter: string | null;
  source_count: number;
  dispatch_configured: boolean;
}

export interface AdminRun {
  id: number;
  name: string | null;
  status: string | null;
  conclusion: string | null;
  created_at: string | null;
  html_url: string | null;
  display_title: string | null;
}
