// Primary axis: the trading style. One hue each, muted + readable on the light surface.
export const CATEGORY_COLOR: Record<string, string> = {
  "Technical Analysis": "var(--color-cat-technical)",
  "Macro Analysis": "var(--color-cat-macro)",
  "Intraday Trading": "var(--color-cat-intraday)",
  "Swing Trading": "var(--color-cat-swing)",
  "Fundamental Analysis": "var(--color-cat-fundamental)",
  "Quant Firms": "var(--color-cat-firms)",
};

export function categoryColor(category: string): string {
  return CATEGORY_COLOR[category] ?? "var(--color-muted)";
}

/** High scores glow with the accent; solid 7-8 stay calm. */
export function scoreColor(score: number): string {
  if (score >= 9) return "var(--color-accent)";
  if (score >= 8) return "var(--color-score-mid)";
  return "var(--color-muted)";
}

export function formatDate(iso?: string | null): string {
  if (!iso) return "";
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return "";
  return d.toLocaleDateString(undefined, { month: "short", day: "numeric", year: "numeric" });
}

export const SOURCE_LABEL: Record<string, string> = {
  github: "GitHub",
  reddit: "Reddit",
  rss: "RSS",
  forum: "Forum",
  mcp: "MCP",
  twitter: "X",
  careers: "Careers",
};

export function sourceLabel(source: string): string {
  return SOURCE_LABEL[source] ?? source;
}
