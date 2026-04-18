import Link from "next/link";
import { TrustBadge } from "@/components/TrustBadge";
import { listMetrics } from "@/lib/api";

export const dynamic = "force-dynamic";

export default async function CatalogPage() {
  const metrics = await listMetrics();

  if (metrics.length === 0) {
    return (
      <div className="mx-auto max-w-3xl px-6 py-16">
        <EmptyState />
      </div>
    );
  }

  return (
    <div className="mx-auto max-w-6xl px-6 py-10">
      <div className="mb-8 flex flex-col gap-3 md:flex-row md:items-end md:justify-between">
        <div>
          <h1 className="text-3xl font-semibold tracking-tight">
            Metric catalog
          </h1>
          <p className="mt-2 max-w-2xl text-neutral-600">
            Every metric with a verified definition, a trust score, and a
            reconciliation against downstream BI tools. Click through for
            lineage and history.
          </p>
        </div>
        <Link
          href="/ask"
          className="inline-flex items-center gap-2 rounded-md border border-violet-200 bg-violet-50 px-3 py-2 text-sm font-medium text-violet-800 hover:bg-violet-100"
        >
          <span
            aria-hidden
            className="inline-block h-2 w-2 rounded-full bg-violet-500"
          />
          Ask about a metric
        </Link>
      </div>

      <div className="grid grid-cols-1 gap-4 md:grid-cols-2 lg:grid-cols-3">
        {metrics.map((m) => {
          const delta = m.value - m.previousValue;
          const pct = m.previousValue === 0 ? 0 : delta / m.previousValue;
          const pctLabel = `${pct >= 0 ? "+" : ""}${(pct * 100).toFixed(1)}%`;
          const deltaClass = pct >= 0 ? "text-trust-pass" : "text-trust-fail";

          return (
            <Link
              key={m.id}
              href={`/metrics/${m.id}`}
              className="group rounded-xl border border-neutral-200 bg-white p-5 shadow-sm transition hover:border-neutral-300 hover:shadow"
            >
              <div className="flex items-start justify-between gap-3">
                <div>
                  <h2 className="text-base font-semibold tracking-tight group-hover:underline">
                    {m.name}
                  </h2>
                  <p className="mt-1 text-xs text-neutral-500">
                    Owned by {m.owner}
                  </p>
                </div>
                <TrustBadge
                  status={m.trustStatus}
                  score={m.trustScore}
                  size="sm"
                />
              </div>
              <div className="mt-4 flex items-baseline gap-3">
                <span className="text-2xl font-semibold tabular-nums">
                  {m.unit === "USD"
                    ? m.value.toLocaleString("en-US", {
                        style: "currency",
                        currency: "USD",
                        maximumFractionDigits: 0,
                      })
                    : m.unit === "%"
                      ? `${m.value.toFixed(2)}%`
                      : `${m.value.toLocaleString("en-US")} ${m.unit}`}
                </span>
                <span className={`text-xs font-medium ${deltaClass}`}>
                  {pctLabel}
                </span>
              </div>
              <p className="mt-3 line-clamp-2 text-sm text-neutral-600">
                {m.description}
              </p>
            </Link>
          );
        })}
      </div>
    </div>
  );
}

/**
 * First-time user empty state. Per blueprint: show install instructions, not
 * a bare table. The dbt path is primary; CLI is the secondary.
 */
function EmptyState() {
  return (
    <div className="rounded-xl border border-dashed border-neutral-300 bg-white p-8 text-center shadow-sm">
      <div className="mx-auto mb-3 inline-flex h-10 w-10 items-center justify-center rounded-full bg-neutral-100 text-neutral-500">
        <svg
          viewBox="0 0 24 24"
          width="20"
          height="20"
          fill="none"
          stroke="currentColor"
          strokeWidth="1.5"
        >
          <path d="M4 4h16v16H4z" />
          <path d="M4 10h16M10 4v16" />
        </svg>
      </div>
      <h2 className="text-xl font-semibold tracking-tight text-neutral-900">
        No metrics yet
      </h2>
      <p className="mx-auto mt-2 max-w-md text-sm text-neutral-600">
        Connect your warehouse and push your first metric definition. The dbt
        package is the fastest path — one `packages.yml` entry and a `dbt run`.
      </p>
      <div className="mt-5 flex flex-wrap items-center justify-center gap-2">
        <Link
          href="/install/dbt"
          className="rounded-md bg-neutral-900 px-4 py-2 text-sm font-medium text-white hover:bg-neutral-800"
        >
          Install in dbt
        </Link>
        <Link
          href="/install/cli"
          className="rounded-md border border-neutral-200 bg-white px-4 py-2 text-sm font-medium text-neutral-800 hover:border-neutral-300 hover:bg-neutral-50"
        >
          Use the standalone CLI
        </Link>
        <Link
          href="/install"
          className="text-sm text-neutral-500 hover:text-neutral-800"
        >
          See all options
        </Link>
      </div>
    </div>
  );
}
