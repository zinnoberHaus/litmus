/**
 * Dummy fixtures for the Litmus UI scaffold.
 *
 * Once the Python API lands, swap the synchronous functions at the bottom of
 * this file for `fetch(...)` calls. Keep the return shapes stable — the
 * components in `components/` are typed against these interfaces.
 */

export type TrustStatus = "pass" | "warn" | "fail";

export interface TrustHistoryPoint {
  /** ISO date, e.g. "2026-04-10" */
  date: string;
  /** 0.0 - 1.0 trust score */
  score: number;
  status: TrustStatus;
}

export interface ReconciliationRow {
  source: string;
  value: number;
  delta: number; // percentage difference vs primary source, e.g. -0.012 = -1.2%
  status: TrustStatus;
}

export interface LineageNode {
  id: string;
  label: string;
  kind: "source" | "transform" | "metric";
}

export interface LineageEdge {
  from: string;
  to: string;
}

export interface Metric {
  id: string;
  name: string;
  description: string;
  owner: string;
  unit: string;
  value: number;
  previousValue: number;
  period: string;
  trustStatus: TrustStatus;
  trustScore: number; // 0 - 1
  lastVerified: string; // ISO timestamp
  definition: {
    source: string;
    given: string[];
    when: string[];
    result: string;
  };
  trustRules: string[];
  history: TrustHistoryPoint[];
  lineage: {
    nodes: LineageNode[];
    edges: LineageEdge[];
  };
  reconciliation: ReconciliationRow[];
  /**
   * Latest run ID + raw status, threaded from the Python API. Used by the
   * "Why did this fail?" panel to POST to ``/runs/:id/explain``. Optional
   * because static fixtures (no server connected) have no run UUIDs.
   */
  latestRun?: {
    id: string;
    /** Raw server status: passed | warning | failed | error. */
    status: string;
  } | null;
}

const mrr: Metric = {
  id: "mrr",
  name: "Monthly Recurring Revenue",
  description:
    "Sum of active subscription revenue, normalized to a monthly cadence.",
  owner: "finance@acme.co",
  unit: "USD",
  value: 482_150,
  previousValue: 461_720,
  period: "March 2026",
  trustStatus: "pass",
  trustScore: 0.98,
  lastVerified: "2026-04-17T08:02:00Z",
  definition: {
    source: "warehouse.stripe.subscriptions",
    given: [
      "status = 'active'",
      "plan.interval IN ('month', 'year')",
    ],
    when: ["subscription is billed in the reporting month"],
    result: "SUM(normalized_monthly_amount) grouped by month",
  },
  trustRules: [
    "freshness < 24 hours",
    "null_rate(customer_id) < 0.1%",
    "row_count > 1000",
    "change vs 30d avg within 15%",
  ],
  history: [
    { date: "2026-03-18", score: 1.0, status: "pass" },
    { date: "2026-03-25", score: 1.0, status: "pass" },
    { date: "2026-04-01", score: 0.9, status: "warn" },
    { date: "2026-04-08", score: 1.0, status: "pass" },
    { date: "2026-04-15", score: 1.0, status: "pass" },
    { date: "2026-04-16", score: 0.98, status: "pass" },
    { date: "2026-04-17", score: 0.98, status: "pass" },
  ],
  lineage: {
    nodes: [
      { id: "stripe", label: "stripe.subscriptions", kind: "source" },
      { id: "stg", label: "stg_subscriptions", kind: "transform" },
      { id: "fct", label: "fct_mrr", kind: "transform" },
      { id: "mrr", label: "Monthly Recurring Revenue", kind: "metric" },
    ],
    edges: [
      { from: "stripe", to: "stg" },
      { from: "stg", to: "fct" },
      { from: "fct", to: "mrr" },
    ],
  },
  reconciliation: [
    { source: "Warehouse (dbt)", value: 482_150, delta: 0, status: "pass" },
    { source: "Looker", value: 481_820, delta: -0.0007, status: "pass" },
    { source: "Tableau", value: 479_900, delta: -0.0047, status: "warn" },
  ],
};

const mau: Metric = {
  id: "mau",
  name: "Monthly Active Users",
  description:
    "Distinct users with at least one qualifying event in the last 30 days.",
  owner: "product@acme.co",
  unit: "users",
  value: 128_402,
  previousValue: 124_001,
  period: "Trailing 30 days",
  trustStatus: "warn",
  trustScore: 0.82,
  lastVerified: "2026-04-17T07:48:00Z",
  definition: {
    source: "warehouse.events.activity",
    given: [
      "event_type IN ('login', 'core_action')",
      "user.is_internal = false",
    ],
    when: ["event occurred within trailing 30 days"],
    result: "COUNT(DISTINCT user_id)",
  },
  trustRules: [
    "freshness < 6 hours",
    "null_rate(user_id) < 0.05%",
    "row_count > 100000",
    "schema_drift = none",
  ],
  history: [
    { date: "2026-03-18", score: 1.0, status: "pass" },
    { date: "2026-03-25", score: 0.9, status: "warn" },
    { date: "2026-04-01", score: 0.95, status: "pass" },
    { date: "2026-04-08", score: 0.8, status: "warn" },
    { date: "2026-04-15", score: 0.78, status: "warn" },
    { date: "2026-04-16", score: 0.82, status: "warn" },
    { date: "2026-04-17", score: 0.82, status: "warn" },
  ],
  lineage: {
    nodes: [
      { id: "events", label: "events.activity", kind: "source" },
      { id: "stg", label: "stg_events", kind: "transform" },
      { id: "dim", label: "dim_users", kind: "transform" },
      { id: "mau", label: "Monthly Active Users", kind: "metric" },
    ],
    edges: [
      { from: "events", to: "stg" },
      { from: "stg", to: "dim" },
      { from: "dim", to: "mau" },
    ],
  },
  reconciliation: [
    { source: "Warehouse (dbt)", value: 128_402, delta: 0, status: "pass" },
    { source: "Looker", value: 126_110, delta: -0.0178, status: "warn" },
    { source: "Tableau", value: 131_090, delta: 0.0209, status: "warn" },
  ],
};

const churn: Metric = {
  id: "churn",
  name: "Gross Monthly Churn",
  description:
    "Percentage of subscriptions canceled or downgraded in the reporting month.",
  owner: "revops@acme.co",
  unit: "%",
  value: 4.2,
  previousValue: 3.8,
  period: "March 2026",
  trustStatus: "fail",
  trustScore: 0.55,
  lastVerified: "2026-04-17T07:31:00Z",
  definition: {
    source: "warehouse.stripe.subscription_events",
    given: ["event IN ('canceled', 'downgraded')"],
    when: ["event occurred in the reporting month"],
    result:
      "canceled_subscriptions / subscriptions_at_start_of_month * 100",
  },
  trustRules: [
    "freshness < 24 hours",
    "row_count > 500",
    "range 0 < value < 20",
    "change vs 90d avg within 25%",
  ],
  history: [
    { date: "2026-03-18", score: 0.9, status: "warn" },
    { date: "2026-03-25", score: 0.85, status: "warn" },
    { date: "2026-04-01", score: 0.7, status: "warn" },
    { date: "2026-04-08", score: 0.6, status: "fail" },
    { date: "2026-04-15", score: 0.55, status: "fail" },
    { date: "2026-04-16", score: 0.55, status: "fail" },
    { date: "2026-04-17", score: 0.55, status: "fail" },
  ],
  lineage: {
    nodes: [
      { id: "stripe", label: "stripe.subscription_events", kind: "source" },
      { id: "stg", label: "stg_subscription_events", kind: "transform" },
      { id: "fct", label: "fct_churn", kind: "transform" },
      { id: "churn", label: "Gross Monthly Churn", kind: "metric" },
    ],
    edges: [
      { from: "stripe", to: "stg" },
      { from: "stg", to: "fct" },
      { from: "fct", to: "churn" },
    ],
  },
  reconciliation: [
    { source: "Warehouse (dbt)", value: 4.2, delta: 0, status: "pass" },
    { source: "Looker", value: 3.9, delta: -0.0714, status: "fail" },
    { source: "Tableau", value: 4.6, delta: 0.0952, status: "fail" },
  ],
};

const METRICS: Record<string, Metric> = {
  mrr,
  mau,
  churn,
};

/**
 * List all metrics in the catalog. Swap for `await fetch('/api/metrics')`
 * once the Python API exists.
 */
export function listMetrics(): Metric[] {
  return Object.values(METRICS);
}

/**
 * Fetch a single metric by id. Returns `null` when not found.
 * Swap for `await fetch('/api/metrics/:id')` once the API exists.
 */
export function getMetric(id: string): Metric | null {
  return METRICS[id] ?? null;
}
