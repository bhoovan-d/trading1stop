import type { ReactNode } from "react";

/** Minimal renderer for the newsletter drafts this app generates (headings, links,
 *  bold, italic, hr, <sub> footers). Not a general-purpose Markdown engine. */
function renderInline(text: string): ReactNode[] {
  const nodes: ReactNode[] = [];
  const re = /(\[([^\]]+)\]\(([^)]+)\))|(\*\*([^*]+)\*\*)/;
  let rest = text;
  let key = 0;
  while (rest.length) {
    const m = rest.match(re);
    if (!m || m.index === undefined) {
      nodes.push(rest);
      break;
    }
    if (m.index > 0) nodes.push(rest.slice(0, m.index));
    if (m[1]) {
      nodes.push(
        <a
          key={key++}
          href={m[3]}
          target="_blank"
          rel="noreferrer"
          className="font-medium text-accent-dim underline decoration-accent-tint decoration-2 underline-offset-[3px] transition-colors hover:decoration-accent"
        >
          {m[2]}
        </a>,
      );
    } else {
      nodes.push(
        <strong key={key++} className="font-semibold text-ink">
          {m[5]}
        </strong>,
      );
    }
    rest = rest.slice(m.index + m[0].length);
  }
  return nodes;
}

function stripTags(s: string): string {
  return s.replace(/<[^>]+>/g, "");
}

export function Markdown({ source }: { source: string }) {
  const lines = source.split("\n");
  const out: ReactNode[] = [];

  lines.forEach((line, i) => {
    const t = line.trim();
    if (t === "") return;
    if (t === "---") {
      out.push(<hr key={i} className="my-10 border-border" />);
    } else if (t.startsWith("### ")) {
      out.push(
        <h3
          key={i}
          className="mt-7 font-serif text-xl font-semibold leading-snug text-ink"
          style={{ fontVariationSettings: '"opsz" 34' }}
        >
          {renderInline(t.slice(4))}
        </h3>,
      );
    } else if (t.startsWith("## ")) {
      out.push(
        <h2 key={i} className="mb-2 mt-12 text-xs font-semibold uppercase tracking-[0.14em] text-accent-dim">
          {t.slice(3)}
        </h2>,
      );
    } else if (t.startsWith("# ")) {
      out.push(
        <h1
          key={i}
          className="font-serif text-3xl font-semibold leading-tight tracking-tight text-ink"
          style={{ fontVariationSettings: '"opsz" 64' }}
        >
          {t.slice(2)}
        </h1>,
      );
    } else if (t.startsWith("<sub>")) {
      out.push(
        <p key={i} className="font-mono text-[11px] text-faint">
          {stripTags(t)}
        </p>,
      );
    } else if ((t.startsWith("*") && t.endsWith("*")) || (t.startsWith("_") && t.endsWith("_"))) {
      out.push(
        <p key={i} className="max-w-[68ch] font-serif text-[17px] italic leading-relaxed text-muted">
          {t.slice(1, -1)}
        </p>,
      );
    } else {
      out.push(
        <p key={i} className="max-w-[68ch] font-serif text-[17px] leading-[1.7] text-ink/90">
          {renderInline(t)}
        </p>,
      );
    }
  });

  return <article className="space-y-3">{out}</article>;
}
