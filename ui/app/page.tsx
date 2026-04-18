import Link from "next/link";
import { CodeBlock } from "@/components/CodeBlock";
import { HeroBadgeDemo } from "@/components/HeroBadgeDemo";
import { Section } from "@/components/Section";

// NOTE(litmus-ui, task #53): Positioning copy below is aligned with the
// blueprint §1.1 / §2.5. If `litmus-advocate` (task #50) ships different
// exact wording in `docs/positioning.md`, update this file to match — the
// docs are the source of truth, this landing quotes from them.

export const metadata = {
  title: "Litmus — Canonical metric contracts",
  description:
    "Canonical metric contracts for engineers, AI-answered questions for PMs, embeddable trust badges for everyone.",
};

const DBT_SNIPPET = `# packages.yml
packages:
  - package: litmus-data/litmus
    version: [">=0.3.0", "<0.4.0"]
`;

const DBT_RUN_SNIPPET = `dbt deps
dbt run --select litmus`;

const CLI_SNIPPET = `pip install litmus-data
litmus init demo-metrics --warehouse duckdb
cd demo-metrics
litmus check metrics/`;

const METRIC_EXAMPLE = `Metric: Monthly Recurring Revenue
Description: Sum of normalized monthly subscription fees.
Owner: finance-analytics

Source: subscriptions

Given the subscription status is "active"
  And the billing interval is monthly or annual

When we calculate
  Then sum the recurring charge amount
  And normalize annual subscriptions by dividing by 12

The result is "Monthly Recurring Revenue"

Trust:
  Freshness must be less than 4 hours
  Row count must not drop more than 5% day over day
  Value must not change more than 20% month over month`;

const BADGE_README_SNIPPET = `![Monthly Recurring Revenue](https://litmus.yourco.com/embed/<token>/badge.svg)`;

export default function LandingPage() {
  return (
    <>
      {/* ───────────────────────── HERO ───────────────────────── */}
      <section className="border-b border-neutral-200 bg-gradient-to-b from-white to-neutral-50">
        <div className="mx-auto max-w-6xl px-6 py-16 md:py-24">
          <div className="grid grid-cols-1 items-center gap-10 lg:grid-cols-2">
            <div>
              <span className="inline-flex items-center gap-1.5 rounded-full bg-neutral-900 px-3 py-1 text-[11px] font-semibold uppercase tracking-wide text-white">
                <span
                  aria-hidden
                  className="inline-block h-1.5 w-1.5 rounded-full bg-trust-pass"
                />
                v0.3 · three audiences, one spec
              </span>
              <h1 className="mt-4 text-4xl font-semibold tracking-tight text-neutral-900 md:text-5xl">
                Canonical metric contracts for engineers,{" "}
                <span className="text-violet-700">
                  AI-answered questions for PMs
                </span>
                ,{" "}
                <span className="text-emerald-700">
                  embeddable trust badges
                </span>{" "}
                for everyone.
              </h1>
              <p className="mt-5 max-w-xl text-lg text-neutral-600">
                Define every business metric as code. Ship a live trust badge.
                Let your PMs ask questions in plain English — with the trust
                status stamped to every answer.
              </p>
              <div className="mt-7 flex flex-wrap items-center gap-3">
                <Link
                  href="/install/dbt"
                  className="inline-flex items-center gap-2 rounded-md bg-neutral-900 px-4 py-2.5 text-sm font-medium text-white shadow-sm hover:bg-neutral-800"
                >
                  Install in dbt
                </Link>
                <Link
                  href="/install/cli"
                  className="inline-flex items-center gap-2 rounded-md border border-neutral-200 bg-white px-4 py-2.5 text-sm font-medium text-neutral-800 shadow-sm hover:border-neutral-300 hover:bg-neutral-50"
                >
                  Try the CLI
                </Link>
                <Link
                  href="/ask"
                  className="inline-flex items-center gap-2 rounded-md border border-violet-200 bg-violet-50 px-4 py-2.5 text-sm font-medium text-violet-800 hover:bg-violet-100"
                >
                  See it live
                </Link>
              </div>
              <p className="mt-6 text-xs text-neutral-500">
                Open source, MIT/Apache. No account required to start.
              </p>
            </div>
            <div className="flex flex-col gap-5">
              <HeroBadgeDemo />
              <div className="rounded-xl border border-neutral-200 bg-white p-2 shadow-sm">
                <CodeBlock
                  caption=".metric"
                  code={METRIC_EXAMPLE}
                  hideCopy
                />
              </div>
            </div>
          </div>
        </div>
      </section>

      <div className="mx-auto max-w-6xl px-6">
        {/* ─────────────────────── ENGINEERS ─────────────────────── */}
        <Section
          tone="engineers"
          eyebrow="For engineers"
          title="Define metrics as code. Run trust checks in dbt or CI."
          description={
            <>
              One spec, two surfaces: the <code>.metric</code> DSL or YAML.
              Every file lowers to the same <code>MetricSpec</code>, so you
              pick the syntax your team already uses — LLMs emit YAML fine,
              PMs read the DSL like English.
            </>
          }
          action={
            <Link
              href="/install"
              className="inline-flex items-center gap-2 rounded-md border border-neutral-200 bg-white px-3 py-2 text-sm font-medium text-neutral-800 hover:border-neutral-300 hover:bg-neutral-50"
            >
              Full install guide &rarr;
            </Link>
          }
          spacious
        >
          <div className="grid grid-cols-1 gap-6 md:grid-cols-2">
            <div className="space-y-4">
              <h3 className="text-sm font-semibold uppercase tracking-wide text-neutral-500">
                dbt package · primary
              </h3>
              <CodeBlock caption="packages.yml" code={DBT_SNIPPET} />
              <CodeBlock caption="your shell" code={DBT_RUN_SNIPPET} />
              <p className="text-sm text-neutral-600">
                Runs trust checks as an <code>on-run-end</code> hook and
                materialises results to <code>litmus_runs</code> +{" "}
                <code>litmus_check_results</code> in your warehouse — no extra
                infra.
              </p>
            </div>
            <div className="space-y-4">
              <h3 className="text-sm font-semibold uppercase tracking-wide text-neutral-500">
                Standalone CLI · no dbt required
              </h3>
              <CodeBlock caption="your shell" code={CLI_SNIPPET} />
              <ul className="space-y-2 text-sm text-neutral-600">
                <li className="flex items-start gap-2">
                  <Check /> Zero-config DuckDB by default.
                </li>
                <li className="flex items-start gap-2">
                  <Check /> Postgres, Snowflake, BigQuery behind extras.
                </li>
                <li className="flex items-start gap-2">
                  <Check /> Ships as a GitHub Action (
                  <code>litmus-data/litmus@v0</code>).
                </li>
              </ul>
            </div>
          </div>

          <div className="mt-8 rounded-xl border border-neutral-200 bg-neutral-50 p-5">
            <h3 className="text-sm font-semibold uppercase tracking-wide text-neutral-700">
              Built-in trust rules
            </h3>
            <p className="mt-1 text-sm text-neutral-600">
              Stateless: freshness, null rate, row count, range, duplicates,
              custom SQL. Stateful: change vs history, schema drift,
              distribution shift.
            </p>
          </div>
        </Section>

        {/* ──────────────────────── PMs ──────────────────────── */}
        <Section
          tone="pm"
          eyebrow="For PMs"
          title="Ask questions. Sign off on definitions. Never open SQL."
          description={
            <>
              The Slack sign-off flow and <code>/ask</code> bot give product
              managers a first-class seat at the metric table — without
              asking them to read YAML or write queries.
            </>
          }
          action={
            <Link
              href="/ask"
              className="inline-flex items-center gap-2 rounded-md bg-violet-600 px-3 py-2 text-sm font-medium text-white shadow-sm hover:bg-violet-700"
            >
              Try the chat &rarr;
            </Link>
          }
          spacious
        >
          <div className="grid grid-cols-1 gap-6 md:grid-cols-2">
            <div className="rounded-xl border border-violet-100 bg-white p-5 shadow-sm">
              <div className="mb-3 flex items-center gap-2 text-xs text-neutral-500">
                <span className="inline-block h-2 w-2 rounded-full bg-violet-500" />
                Slack · #data-questions
              </div>
              <div className="space-y-3 text-sm">
                <SlackBubble user="alice" time="9:42">
                  /ask what was revenue last month?
                </SlackBubble>
                <SlackBubble user="litmus" time="9:42" bot>
                  Monthly Recurring Revenue for March 2026 was{" "}
                  <strong>$4.22M</strong>. Trust is{" "}
                  <span className="font-semibold text-trust-pass">green</span>.
                  (5/5 checks passed in the 03-31 run.)
                </SlackBubble>
                <SlackBubble user="alice" time="9:43">
                  sign off: approve the new churn formula
                </SlackBubble>
              </div>
            </div>
            <div className="rounded-xl border border-violet-100 bg-white p-5 shadow-sm">
              <h3 className="text-sm font-semibold uppercase tracking-wide text-neutral-700">
                /ask — answers with provenance
              </h3>
              <p className="mt-2 text-sm text-neutral-600">
                Plain-English question in. Warehouse-backed answer out —
                stamped with the trust status and a link to the canonical
                metric definition so anyone can audit the number.
              </p>
              <div className="mt-4 rounded-lg border border-neutral-200 bg-neutral-50 p-3 text-xs text-neutral-600">
                <div className="font-mono text-neutral-500">
                  POST /api/v1/ask
                </div>
                <div className="mt-1 font-mono text-neutral-800">
                  {"{ question, metric_slug? } → { answer, trust_status, definition_url, … }"}
                </div>
              </div>
              <div className="mt-4 flex flex-wrap gap-2">
                <Badge tone="violet">Slack sign-off</Badge>
                <Badge tone="violet">/ask bot</Badge>
                <Badge tone="violet">AI with provenance</Badge>
              </div>
              <Link
                href="/ask"
                className="mt-4 inline-flex items-center gap-1 text-sm font-medium text-violet-700 hover:text-violet-900"
              >
                Open the chat &rarr;
              </Link>
            </div>
          </div>
        </Section>

        {/* ─────────────────────── VIEWERS ─────────────────────── */}
        <Section
          tone="viewers"
          eyebrow="For everyone"
          title="Trust, embedded anywhere there's a URL."
          description="One SVG, a thousand places. The Litmus badge renders in Notion, Slack unfurls, Confluence, GitHub READMEs, and any markdown surface — and every rendered badge is a backlink to the live metric."
          action={
            <Link
              href="/badge"
              className="inline-flex items-center gap-2 rounded-md border border-emerald-200 bg-emerald-50 px-3 py-2 text-sm font-medium text-emerald-800 hover:bg-emerald-100"
            >
              Open the badge gallery &rarr;
            </Link>
          }
          spacious
        >
          <div className="grid grid-cols-1 gap-6 md:grid-cols-2">
            <div className="space-y-4">
              <CodeBlock caption="README.md" code={BADGE_README_SNIPPET} />
              <p className="text-sm text-neutral-600">
                Copy-paste for Notion, Slack, Confluence, and GitHub README on
                the dedicated{" "}
                <Link
                  href="/badge"
                  className="underline underline-offset-2"
                >
                  badge page
                </Link>
                .
              </p>
            </div>
            <div className="rounded-xl border border-emerald-100 bg-white p-5 shadow-sm">
              <h3 className="text-sm font-semibold uppercase tracking-wide text-neutral-700">
                Powered by Litmus — the viral loop
              </h3>
              <ul className="mt-3 space-y-2 text-sm text-neutral-600">
                <li className="flex items-start gap-2">
                  <Check />
                  Every rendered badge carries a backlink to the live metric
                  page.
                </li>
                <li className="flex items-start gap-2">
                  <Check />
                  Three sizes — sm / md / lg — so it fits anywhere.
                </li>
                <li className="flex items-start gap-2">
                  <Check />
                  Auto-refreshes on every run (public repos: via GitHub
                  webhook).
                </li>
              </ul>
            </div>
          </div>
        </Section>

        {/* ─────────────────── SOCIAL PROOF (stub) ─────────────────── */}
        <Section
          tone="neutral"
          eyebrow="Open source"
          title="Built in the open"
          description="Community grid — we'll fill this with logos once teams opt-in. In the meantime: star the repo on GitHub, follow releases on PyPI, and hit the CFP at Coalesce 2026."
        >
          <div className="grid grid-cols-2 gap-3 md:grid-cols-4">
            <PlaceholderLogo label="Your team?" />
            <PlaceholderLogo label="Your team?" />
            <PlaceholderLogo label="Your team?" />
            <PlaceholderLogo label="Your team?" />
          </div>
        </Section>
      </div>
    </>
  );
}

function Check() {
  return (
    <svg
      viewBox="0 0 20 20"
      className="mt-0.5 h-4 w-4 flex-shrink-0 text-trust-pass"
      fill="currentColor"
      aria-hidden
    >
      <path
        fillRule="evenodd"
        clipRule="evenodd"
        d="M16.704 5.29a1 1 0 010 1.42l-7.07 7.07a1 1 0 01-1.415 0L3.293 8.864a1 1 0 111.414-1.414l3.22 3.222 6.362-6.364a1 1 0 011.415 0z"
      />
    </svg>
  );
}

function Badge({
  tone,
  children,
}: {
  tone: "violet" | "emerald" | "indigo";
  children: React.ReactNode;
}) {
  const map = {
    violet: "bg-violet-50 text-violet-800 ring-violet-200",
    emerald: "bg-emerald-50 text-emerald-800 ring-emerald-200",
    indigo: "bg-indigo-50 text-indigo-800 ring-indigo-200",
  };
  return (
    <span
      className={`inline-flex items-center rounded-full px-2.5 py-1 text-[11px] font-medium ring-1 ${map[tone]}`}
    >
      {children}
    </span>
  );
}

function SlackBubble({
  user,
  time,
  bot,
  children,
}: {
  user: string;
  time: string;
  bot?: boolean;
  children: React.ReactNode;
}) {
  return (
    <div className="flex gap-3">
      <div
        className={`mt-0.5 inline-flex h-7 w-7 flex-shrink-0 items-center justify-center rounded-md text-xs font-semibold text-white ${
          bot ? "bg-violet-600" : "bg-neutral-800"
        }`}
      >
        {bot ? "L" : user[0].toUpperCase()}
      </div>
      <div>
        <div className="text-xs text-neutral-500">
          <span className="font-semibold text-neutral-800">{user}</span>{" "}
          <span className="text-neutral-400">· {time} AM</span>
        </div>
        <div className="mt-0.5 text-sm text-neutral-800">{children}</div>
      </div>
    </div>
  );
}

function PlaceholderLogo({ label }: { label: string }) {
  return (
    <div className="flex h-16 items-center justify-center rounded-lg border border-dashed border-neutral-200 bg-white text-xs text-neutral-400">
      {label}
    </div>
  );
}
