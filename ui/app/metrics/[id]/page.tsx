import Link from "next/link";
import { notFound } from "next/navigation";
import { LineageGraph } from "@/components/LineageGraph";
import { ReconciliationPanel } from "@/components/ReconciliationPanel";
import { TrustBadge } from "@/components/TrustBadge";
import { TrustHistoryChart } from "@/components/TrustHistoryChart";
import { WhyDidThisFail } from "@/components/WhyDidThisFail";
import { getMetric, getRunExplanation } from "@/lib/api";

export const dynamic = "force-dynamic";

interface MetricPageProps {
  params: Promise<{ id: string }>;
}

function formatPrimary(value: number, unit: string): string {
  if (unit === "USD") {
    return value.toLocaleString("en-US", {
      style: "currency",
      currency: "USD",
      maximumFractionDigits: 0,
    });
  }
  if (unit === "%") {
    return `${value.toFixed(2)}%`;
  }
  return `${value.toLocaleString("en-US")} ${unit}`;
}

function formatTimestamp(iso: string): string {
  return new Date(iso).toLocaleString("en-US", {
    dateStyle: "medium",
    timeStyle: "short",
  });
}

export default async function MetricDetailPage({ params }: MetricPageProps) {
  const { id } = await params;
  const metric = await getMetric(id);
  if (!metric) return notFound();

  const delta = metric.value - metric.previousValue;
  const pct =
    metric.previousValue === 0 ? 0 : delta / metric.previousValue;
  const pctLabel = `${pct >= 0 ? "+" : ""}${(pct * 100).toFixed(1)}%`;
  const deltaClass = pct >= 0 ? "text-trust-pass" : "text-trust-fail";

  // If the latest run failed, preload any cached explanation server-side so the
  // UI renders the hypothesis immediately on navigation (no flash of "click
  // to explain" when we've already paid for the answer).
  const latestRun = metric.latestRun ?? null;
  const latestStatus = latestRun?.status?.toLowerCase() ?? "";
  const showExplainer =
    latestRun != null &&
    (latestStatus === "failed" ||
      latestStatus === "error" ||
      latestStatus === "errored");
  const initialExplanation = showExplainer
    ? await getRunExplanation(latestRun.id)
    : null;

  return (
    <div className="space-y-8">
      <div>
        <Link
          href="/"
          className="text-sm text-neutral-500 hover:text-neutral-800"
        >
          &larr; Back to catalog
        </Link>
      </div>

      {/* Header */}
      <header className="flex flex-col gap-4 md:flex-row md:items-start md:justify-between">
        <div>
          <div className="flex items-center gap-3">
            <h1 className="text-3xl font-semibold tracking-tight">
              {metric.name}
            </h1>
            <TrustBadge
              status={metric.trustStatus}
              score={metric.trustScore}
            />
          </div>
          <p className="mt-2 max-w-2xl text-neutral-600">
            {metric.description}
          </p>
          <p className="mt-2 text-xs text-neutral-500">
            Owner: {metric.owner} &middot; Last verified{" "}
            {formatTimestamp(metric.lastVerified)}
          </p>
        </div>

        <div className="rounded-xl border border-neutral-200 bg-white p-5">
          <div className="text-xs uppercase tracking-wide text-neutral-500">
            {metric.period}
          </div>
          <div className="mt-1 text-3xl font-semibold tabular-nums">
            {formatPrimary(metric.value, metric.unit)}
          </div>
          <div className={`mt-1 text-sm font-medium ${deltaClass}`}>
            {pctLabel} vs previous period
          </div>
          <div className="mt-3 text-[11px] font-mono text-neutral-500">
            Embed:&nbsp;
            <code>/embed/{metric.id}</code>
          </div>
        </div>
      </header>

      {/* Reconciliation — surfaced up high; disagreement is the #1 trust signal. */}
      <ReconciliationPanel
        rows={metric.reconciliation}
        unit={metric.unit}
      />

      {showExplainer && latestRun && (
        <WhyDidThisFail
          runId={latestRun.id}
          status={latestRun.status}
          initial={initialExplanation}
        />
      )}

      {/* The three "tabs" the mockup called for, rendered as sections. */}
      <section
        id="definition"
        className="rounded-xl border border-neutral-200 bg-white p-5"
      >
        <h2 className="text-sm font-semibold uppercase tracking-wide text-neutral-700">
          Definition
        </h2>
        <dl className="mt-3 grid grid-cols-1 gap-4 text-sm md:grid-cols-[120px_1fr]">
          <dt className="text-neutral-500">Source</dt>
          <dd className="font-mono text-neutral-800">
            {metric.definition.source}
          </dd>

          <dt className="text-neutral-500">Given</dt>
          <dd>
            <ul className="space-y-1 font-mono text-neutral-800">
              {metric.definition.given.map((g, i) => (
                <li key={i}>{g}</li>
              ))}
            </ul>
          </dd>

          <dt className="text-neutral-500">When</dt>
          <dd>
            <ul className="space-y-1 font-mono text-neutral-800">
              {metric.definition.when.map((w, i) => (
                <li key={i}>{w}</li>
              ))}
            </ul>
          </dd>

          <dt className="text-neutral-500">Result</dt>
          <dd className="font-mono text-neutral-800">
            {metric.definition.result}
          </dd>

          <dt className="text-neutral-500">Trust rules</dt>
          <dd>
            <ul className="space-y-1 font-mono text-neutral-800">
              {metric.trustRules.map((r, i) => (
                <li key={i}>- {r}</li>
              ))}
            </ul>
          </dd>
        </dl>
      </section>

      <section
        id="trust-history"
        className="rounded-xl border border-neutral-200 bg-white p-5"
      >
        <div className="flex items-start justify-between">
          <div>
            <h2 className="text-sm font-semibold uppercase tracking-wide text-neutral-700">
              Trust history
            </h2>
            <p className="mt-1 text-sm text-neutral-600">
              Score over time. Green band = passing, yellow = warning,
              red = failing.
            </p>
          </div>
          <div className="font-mono text-xs text-neutral-500">
            latest {(metric.trustScore * 100).toFixed(0)}
          </div>
        </div>
        <div className="mt-4">
          <TrustHistoryChart history={metric.history} />
        </div>
      </section>

      <section
        id="lineage"
        className="rounded-xl border border-neutral-200 bg-white p-5"
      >
        <h2 className="text-sm font-semibold uppercase tracking-wide text-neutral-700">
          Lineage
        </h2>
        <p className="mt-1 text-sm text-neutral-600">
          Data flow from source to metric. In production this will be a
          clickable DAG with column-level links.
        </p>
        <div className="mt-4 overflow-x-auto">
          <LineageGraph
            nodes={metric.lineage.nodes}
            edges={metric.lineage.edges}
          />
        </div>
      </section>
    </div>
  );
}
