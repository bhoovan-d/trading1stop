export interface Insight {
  id: number;
  relevance_score: number;
  category: string;
  approaches: string[];
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
