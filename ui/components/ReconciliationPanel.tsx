import type { ReconciliationRow } from "@/lib/fixtures";
import { TrustBadge } from "./TrustBadge";

interface ReconciliationPanelProps {
  rows: ReconciliationRow[];
  unit: string;
}

function formatValue(value: number, unit: string): string {
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

function formatDelta(delta: number): string {
  if (delta === 0) return "baseline";
  const sign = delta > 0 ? "+" : "";
  return `${sign}${(delta * 100).toFixed(2)}%`;
}

/**
 * Surfaces the cross-source reconciliation warning — if the warehouse, Looker
 * and Tableau disagree, we want that in the user's face on the metric page.
 */
export function ReconciliationPanel({
  rows,
  unit,
}: ReconciliationPanelProps) {
  const hasDisagreement = rows.some((r) => r.status !== "pass");

  return (
    <section
      className={`rounded-xl border p-5 ${
        hasDisagreement
          ? "border-yellow-300 bg-yellow-50/60"
          : "border-neutral-200 bg-white"
      }`}
    >
      <div className="mb-3 flex items-start justify-between gap-4">
        <div>
          <h3 className="text-sm font-semibold uppercase tracking-wide text-neutral-700">
            Cross-source reconciliation
          </h3>
          <p className="mt-1 text-sm text-neutral-600">
            {hasDisagreement
              ? "Sources disagree. Investigate before publishing this number."
              : "All sources agree within tolerance."}
          </p>
        </div>
        <TrustBadge
          status={hasDisagreement ? "warn" : "pass"}
          size="sm"
          label={hasDisagreement ? "Disagreement" : "Aligned"}
        />
      </div>
      <table className="w-full text-sm">
        <thead className="text-left text-xs uppercase tracking-wide text-neutral-500">
          <tr>
            <th className="pb-2 pr-4 font-medium">Source</th>
            <th className="pb-2 pr-4 font-medium">Value</th>
            <th className="pb-2 pr-4 font-medium">Delta</th>
            <th className="pb-2 font-medium">Status</th>
          </tr>
        </thead>
        <tbody>
          {rows.map((r) => (
            <tr key={r.source} className="border-t border-neutral-200/60">
              <td className="py-2 pr-4">{r.source}</td>
              <td className="py-2 pr-4 font-mono text-neutral-800">
                {formatValue(r.value, unit)}
              </td>
              <td className="py-2 pr-4 font-mono text-neutral-600">
                {formatDelta(r.delta)}
              </td>
              <td className="py-2">
                <TrustBadge status={r.status} size="sm" />
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </section>
  );
}
