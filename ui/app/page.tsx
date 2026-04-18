import Link from "next/link";
import { TrustBadge } from "@/components/TrustBadge";
import { listMetrics } from "@/lib/api";

export const dynamic = "force-dynamic";

export default async function CatalogPage() {
  const metrics = await listMetrics();

  return (
    <div>
      <div className="mb-8">
        <h1 className="text-3xl font-semibold tracking-tight">
          Metric catalog
        </h1>
        <p className="mt-2 max-w-2xl text-neutral-600">
          Every metric with a verified definition, a trust score, and a
          reconciliation against downstream BI tools. Click through for
          lineage and history.
        </p>
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
