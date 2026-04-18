import { CodeBlock } from "@/components/CodeBlock";

// NOTE(litmus-ui, task #53): The badge SVG rendering details (size variants,
// title/desc tags, viral-loop backlink) are owned by task #55 (badge polish).
// This page is the copy-paste surface; it renders whatever SVG the API / the
// `/embed/[id]` route ships. If #55 changes the default size or adds new
// states, add the corresponding row below.

export const metadata = {
  title: "Litmus badge gallery",
  description:
    "Copy-paste Litmus trust badges into Notion, Slack, Confluence, GitHub READMEs, or any markdown surface.",
};

const STATES = [
  {
    label: "trusted",
    tone: "passed",
    fill: "#16a34a",
    description: "All trust checks passed in the latest run.",
  },
  {
    label: "review",
    tone: "warning",
    fill: "#ca8a04",
    description:
      "At least one rule is within 90% of its threshold — worth a look.",
  },
  {
    label: "broken",
    tone: "failed",
    fill: "#dc2626",
    description: "One or more rules failed in the latest run.",
  },
  {
    label: "unknown",
    tone: "unknown",
    fill: "#737373",
    description: "No runs yet, or the warehouse was unreachable.",
  },
] as const;

const SIZES = [
  { name: "sm", label: "Compact", height: 22, total: 180 },
  { name: "md", label: "Default", height: 28, total: 220 },
  { name: "lg", label: "Large", height: 40, total: 320 },
] as const;

const README_SNIPPET = `![Monthly Recurring Revenue](https://litmus.yourco.com/embed/<token>/badge.svg)`;

const HTML_SNIPPET = `<a href="https://litmus.yourco.com/metrics/monthly_revenue">
  <img
    alt="Litmus trust: Monthly Recurring Revenue"
    src="https://litmus.yourco.com/embed/<token>/badge.svg"
    height="28"
  />
</a>`;

const NOTION_SNIPPET = `https://litmus.yourco.com/embed/<token>/badge.svg`;

const SLACK_SNIPPET = `https://litmus.yourco.com/metrics/monthly_revenue
# Slack unfurls this URL into a card containing the live badge.`;

const CONFLUENCE_SNIPPET = `{html}
<img
  alt="Litmus trust"
  src="https://litmus.yourco.com/embed/<token>/badge.svg"
  height="28"
/>
{html}`;

export default function BadgePage() {
  return (
    <div className="mx-auto max-w-5xl px-6 py-10 space-y-12">
      <header>
        <span className="inline-flex items-center gap-1.5 rounded-full bg-emerald-50 px-2.5 py-1 text-[11px] font-semibold uppercase tracking-wide text-emerald-700 ring-1 ring-emerald-200">
          For everyone · Badge gallery
        </span>
        <h1 className="mt-3 text-3xl font-semibold tracking-tight">
          Trust, embedded anywhere there&rsquo;s a URL
        </h1>
        <p className="mt-2 max-w-2xl text-neutral-600">
          One SVG, every surface. Grab a copy-paste snippet for Notion, Slack,
          Confluence, or a GitHub README. Every rendered badge is a backlink
          to the live metric.
        </p>
      </header>

      {/* ───────── States ───────── */}
      <section>
        <h2 className="text-sm font-semibold uppercase tracking-wide text-neutral-700">
          Badge states
        </h2>
        <div className="mt-4 grid grid-cols-1 gap-3 md:grid-cols-2">
          {STATES.map((s) => (
            <div
              key={s.label}
              className="flex items-center gap-4 rounded-xl border border-neutral-200 bg-white p-4 shadow-sm"
            >
              <BadgeSvg label={s.label} fill={s.fill} height={28} />
              <div className="flex-1">
                <div className="text-sm font-medium capitalize text-neutral-900">
                  {s.label}
                </div>
                <div className="text-xs text-neutral-600">{s.description}</div>
                <div className="mt-1 text-[10px] font-mono uppercase tracking-wide text-neutral-400">
                  status = {s.tone}
                </div>
              </div>
            </div>
          ))}
        </div>
      </section>

      {/* ───────── Sizes ───────── */}
      <section>
        <h2 className="text-sm font-semibold uppercase tracking-wide text-neutral-700">
          Sizes
        </h2>
        <div className="mt-4 flex flex-wrap items-end gap-6 rounded-xl border border-neutral-200 bg-white p-6 shadow-sm">
          {SIZES.map((sz) => (
            <div key={sz.name} className="flex flex-col items-start gap-2">
              <BadgeSvg
                label="trusted"
                fill="#16a34a"
                height={sz.height}
                total={sz.total}
              />
              <div className="text-xs text-neutral-600">
                <span className="font-mono text-neutral-800">{sz.name}</span>{" "}
                · {sz.label}
              </div>
            </div>
          ))}
        </div>
        <p className="mt-3 text-xs text-neutral-500">
          Append <code>?size=sm|md|lg</code> to the embed URL. Default is{" "}
          <code>md</code>.
        </p>
      </section>

      {/* ───────── Snippets ───────── */}
      <section className="space-y-6">
        <h2 className="text-sm font-semibold uppercase tracking-wide text-neutral-700">
          Copy-paste snippets
        </h2>

        <Snippet
          title="GitHub README"
          description="Markdown image — renders inline with your shields.io-style badges."
          code={README_SNIPPET}
          caption="README.md"
        />

        <Snippet
          title="HTML (any docs site)"
          description="Wrapped in an anchor so the badge links to the live metric. Works in Confluence HTML blocks, GitHub Pages, and most static docs generators."
          code={HTML_SNIPPET}
          caption="page.html"
        />

        <Snippet
          title="Notion"
          description="Use /embed in Notion, paste the raw SVG URL. Notion keeps the image live-refreshing on page load."
          code={NOTION_SNIPPET}
          caption="Notion · /embed"
        />

        <Snippet
          title="Slack"
          description="Paste the metric URL into any channel. Slack unfurls it into a card showing the badge + current value."
          code={SLACK_SNIPPET}
          caption="Slack · any channel"
        />

        <Snippet
          title="Confluence"
          description="Drop an HTML macro (requires the HTML macro to be enabled for your space)."
          code={CONFLUENCE_SNIPPET}
          caption="Confluence · {html} macro"
        />
      </section>

      <aside className="rounded-xl border border-neutral-200 bg-neutral-50 p-4 text-sm text-neutral-700">
        <div className="font-semibold text-neutral-900">
          Powered by Litmus — the viral loop
        </div>
        <p className="mt-1 text-neutral-600">
          Every rendered badge wraps in an{" "}
          <code>&lt;a xlink:href&gt;</code> linking back to the metric page.
          Works in README and Confluence; Notion strips the anchor but the{" "}
          <code>&lt;title&gt;</code>/<code>&lt;desc&gt;</code> text
          breadcrumbs stay. No tracking pixel, no analytics beacon — the loop
          is purely the URL.
        </p>
      </aside>
    </div>
  );
}

function Snippet({
  title,
  description,
  code,
  caption,
}: {
  title: string;
  description: string;
  code: string;
  caption: string;
}) {
  return (
    <div className="rounded-xl border border-neutral-200 bg-white p-5 shadow-sm">
      <div className="mb-2">
        <h3 className="text-sm font-semibold text-neutral-900">{title}</h3>
        <p className="mt-1 text-xs text-neutral-600">{description}</p>
      </div>
      <CodeBlock caption={caption} code={code} />
    </div>
  );
}

/**
 * Hand-rendered shields-style badge so this page works without fetching any
 * upstream SVG. Mirrors the palette + shape from the embed route.
 */
function BadgeSvg({
  label,
  fill,
  height,
  total,
}: {
  label: string;
  fill: string;
  height: number;
  total?: number;
}) {
  const leftText = "litmus";
  const leftW = Math.max(56, leftText.length * 7 + 14);
  const rightW = Math.max(60, label.length * 7 + 16);
  const finalTotal = total ?? leftW + rightW;
  const lW = total ? Math.floor(finalTotal * 0.4) : leftW;
  const rW = finalTotal - lW;
  const fontSize = Math.max(10, Math.round(height / 2.1));
  return (
    <svg
      width={finalTotal}
      height={height}
      viewBox={`0 0 ${finalTotal} ${height}`}
      role="img"
      aria-label={`litmus ${label}`}
      className="overflow-hidden rounded"
    >
      <rect width={lW} height={height} fill="#1f2937" />
      <rect x={lW} width={rW} height={height} fill={fill} />
      <g
        fill="#fff"
        textAnchor="middle"
        fontFamily="ui-sans-serif,system-ui,-apple-system,Segoe UI,Roboto,sans-serif"
        fontSize={fontSize}
      >
        <text x={lW / 2} y={height / 2 + fontSize / 3}>
          {leftText}
        </text>
        <text x={lW + rW / 2} y={height / 2 + fontSize / 3}>
          {label}
        </text>
      </g>
    </svg>
  );
}
