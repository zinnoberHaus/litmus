/**
 * Live Litmus API client for the UI.
 *
 * Reads `LITMUS_API_INTERNAL` (set inside docker-compose so SSR can reach the
 * API by service name) with a fallback to `NEXT_PUBLIC_LITMUS_API` for local
 * dev. If both are unset or the API is unreachable, we fall back to static
 * fixtures so the UI keeps rendering in demo mode.
 */

import { getMetric as getFixtureMetric, listMetrics as listFixtureMetrics } from "./fixtures";
import type {
  LineageEdge,
  LineageNode,
  Metric,
  ReconciliationRow,
  TrustHistoryPoint,
  TrustStatus,
} from "./fixtures";

export type { Metric, TrustStatus } from "./fixtures";

interface LatestRunPayload {
  id: string;
  status: string;
  trust_score: number | null;
  started_at: string | null;
  finished_at: string | null;
  value_sum: number | null;
  row_count: number | null;
}

interface MetricPayload {
  id: string;
  slug: string;
  name: string;
  description: string | null;
  owner_email: string | null;
  primary_table: string | null;
  spec: Record<string, unknown>;
  source_repo: string | null;
  source_path: string | null;
  source_sha: string | null;
  created_at: string;
  updated_at: string;
  latest_run: LatestRunPayload | null;
  embed_token: string | null;
}

interface RunPayload {
  id: string;
  status: string;
  trust_score: number | null;
  started_at: string;
  value_sum: number | null;
  row_count: number | null;
}

function apiBase(): string | null {
  // Server-side can hit the in-cluster URL; client-side uses the public one.
  if (typeof window === "undefined") {
    return process.env.LITMUS_API_INTERNAL ?? process.env.NEXT_PUBLIC_LITMUS_API ?? null;
  }
  return process.env.NEXT_PUBLIC_LITMUS_API ?? null;
}

function mapStatus(raw: string | null | undefined): TrustStatus {
  const s = (raw ?? "unknown").toLowerCase();
  if (s === "passed" || s === "pass") return "pass";
  if (s === "warning" || s === "warn") return "warn";
  if (s === "failed" || s === "fail" || s === "error") return "fail";
  return "warn";
}

interface TrustSpecPayload {
  freshness?: { max_hours?: number } | null;
  null_rules?: { column?: string; max_percentage?: number }[];
  volume_rules?: {
    max_drop_percentage?: number;
    period?: string;
    table?: string | null;
  }[];
  range_rules?: { min_value?: number; max_value?: number }[];
  change_rules?: { max_change_percentage?: number; period?: string }[];
  duplicate_rules?: { column?: string; max_percentage?: number }[];
  schema_drift?: Record<string, unknown> | null;
  distribution_shift_rules?: {
    column?: string;
    max_change_percentage?: number;
    period?: string;
  }[];
}

function describeTrustRules(spec: Record<string, unknown>): string[] {
  const trust = spec["trust"] as TrustSpecPayload | null | undefined;
  if (!trust) return [];
  const rules: string[] = [];
  if (trust.freshness?.max_hours !== undefined) {
    rules.push(`freshness < ${trust.freshness.max_hours} hours`);
  }
  for (const r of trust.null_rules ?? []) {
    rules.push(`null_rate(${r.column ?? "?"}) < ${r.max_percentage ?? "?"}%`);
  }
  for (const r of trust.volume_rules ?? []) {
    const tbl = r.table ?? "primary";
    rules.push(
      `row_count(${tbl}) drop < ${r.max_drop_percentage ?? "?"}% ${r.period ?? ""}`.trim(),
    );
  }
  for (const r of trust.range_rules ?? []) {
    rules.push(`value ∈ [${r.min_value ?? "?"}, ${r.max_value ?? "?"}]`);
  }
  for (const r of trust.change_rules ?? []) {
    rules.push(`change < ${r.max_change_percentage ?? "?"}% ${r.period ?? ""}`.trim());
  }
  for (const r of trust.duplicate_rules ?? []) {
    rules.push(`duplicates(${r.column ?? "?"}) < ${r.max_percentage ?? "?"}%`);
  }
  if (trust.schema_drift) rules.push("schema_drift = none");
  for (const r of trust.distribution_shift_rules ?? []) {
    rules.push(
      `dist_shift(${r.column ?? "?"}) < ${r.max_change_percentage ?? "?"}% ${r.period ?? ""}`.trim(),
    );
  }
  return rules;
}

function stubLineage(primaryTable: string | null, metricName: string): {
  nodes: LineageNode[];
  edges: LineageEdge[];
} {
  // Fallback used when the API is unreachable or lineage hasn't been
  // imported yet. The API itself also returns a 2-node stub for metrics
  // without a real graph, so the UI renders consistently in both modes.
  const source = primaryTable ?? "source_table";
  return {
    nodes: [
      { id: "src", label: source, kind: "source" },
      { id: "metric", label: metricName, kind: "metric" },
    ],
    edges: [{ from: "src", to: "metric" }],
  };
}

interface LineageNodePayload {
  id: string;
  label: string;
  // API emits "source" | "model" | "metric" — we widen to the UI's local
  // type which still includes "transform" for legacy fixtures.
  kind: string;
}

interface LineageEdgePayload {
  from: string;
  to: string;
}

interface LineagePayload {
  nodes: LineageNodePayload[];
  edges: LineageEdgePayload[];
}

function mapLineageKind(kind: string): LineageNode["kind"] {
  if (kind === "source" || kind === "metric" || kind === "transform") {
    return kind;
  }
  // The server emits "model" for intermediate dbt nodes; the UI's
  // existing fixtures use "transform" for the same idea. Map so the
  // graph component renders without a new case.
  if (kind === "model") return "transform";
  return "transform";
}

/**
 * Fetch the lineage subgraph for a metric from the Python API.
 *
 * The API always returns at least a 2-node stub (source → metric), so
 * callers never need to handle an empty graph — they still get a placeholder
 * that renders cleanly. Returns ``null`` only if the API is unreachable.
 */
export async function getLineage(
  id: string,
): Promise<{ nodes: LineageNode[]; edges: LineageEdge[] } | null> {
  const base = apiBase();
  if (!base) return null;
  try {
    const payload = await fetchJson<LineagePayload>(
      `${base}/api/v1/metrics/${id}/lineage`,
    );
    return {
      nodes: payload.nodes.map((n) => ({
        id: n.id,
        label: n.label,
        kind: mapLineageKind(n.kind),
      })),
      edges: payload.edges.map((e) => ({ from: e.from, to: e.to })),
    };
  } catch (err) {
    console.warn(`getLineage(${id}): API unreachable:`, err);
    return null;
  }
}

function toMetricCard(
  m: MetricPayload,
  history: TrustHistoryPoint[],
  lineage?: { nodes: LineageNode[]; edges: LineageEdge[] } | null,
  reconciliation?: ReconciliationRow[] | null,
): Metric {
  const spec = m.spec ?? {};
  const sources = (spec["sources"] as string[] | undefined) ?? [];
  const calculations = (spec["calculations"] as string[] | undefined) ?? [];
  const conditions = (spec["conditions"] as string[] | undefined) ?? [];
  const latest = m.latest_run;

  const trustStatus = mapStatus(latest?.status);
  const trustScore = latest?.trust_score ?? 0;
  const value = latest?.value_sum ?? latest?.row_count ?? 0;
  const lastVerified = latest?.started_at ?? m.updated_at;

  // The reconciliation panel must never be empty — users expect to always
  // see at least the warehouse row. Fall back to the local stub when the
  // API call failed or returned no rows.
  const resolvedReconciliation =
    reconciliation && reconciliation.length > 0
      ? reconciliation
      : reconciliationFallback(trustStatus, value);

  return {
    id: m.slug,
    name: m.name,
    description: m.description ?? "",
    owner: m.owner_email ?? "unowned",
    unit: "",
    value,
    previousValue: value,
    period: latest?.started_at ? new Date(latest.started_at).toDateString() : "—",
    trustStatus,
    trustScore,
    lastVerified,
    definition: {
      source: m.primary_table ?? sources[0] ?? "—",
      given: conditions.length > 0 ? conditions : [`records from ${sources.join(", ") || "source"}`],
      when: calculations.length > 0 ? calculations : ["calculate per-run aggregate"],
      result: (spec["result_name"] as string | undefined) ?? m.name,
    },
    trustRules: describeTrustRules(spec),
    history,
    // Prefer the API's real lineage; fall back to a local stub so the UI
    // always renders a graph even when the API is down.
    lineage: lineage ?? stubLineage(m.primary_table, m.name),
    reconciliation: resolvedReconciliation,
    latestRun: latest ? { id: latest.id, status: latest.status } : null,
  };
}

function reconciliationFallback(status: TrustStatus, value: number): ReconciliationRow[] {
  // Fallback used when the API is unreachable or returned no rows. The live
  // path (``getReconciliation``) always includes a synthetic warehouse row,
  // so this is only exercised in demo mode or after a transport failure.
  return [{ source: "Warehouse (Litmus)", value, delta: 0, status }];
}

interface ReconciliationRowPayload {
  source: string;
  value: number;
  delta: number;
  status: string;
  identifier?: string | null;
  error?: string | null;
  recorded_at?: string | null;
}

function prettifySource(source: string): string {
  if (source === "warehouse") return "Warehouse (Litmus)";
  if (source === "looker") return "Looker";
  if (source === "tableau") return "Tableau";
  // Fallback: capitalize whatever the server sent so new BI tools render
  // with a sane label until the UI grows an explicit case for them.
  return source.charAt(0).toUpperCase() + source.slice(1);
}

/**
 * Fetch the latest reconciliation rows for a metric.
 *
 * The API always includes a synthetic ``"warehouse"`` row at the top, so a
 * successful fetch is guaranteed to be non-empty. Returns ``null`` only if
 * the transport itself fails — callers should fall back to the local stub
 * in that case so the panel still renders.
 */
export async function getReconciliation(
  id: string,
): Promise<ReconciliationRow[] | null> {
  const base = apiBase();
  if (!base) return null;
  try {
    const payload = await fetchJson<ReconciliationRowPayload[]>(
      `${base}/api/v1/metrics/${id}/reconciliation`,
    );
    return payload.map((r) => ({
      source: prettifySource(r.source),
      value: r.value,
      delta: r.delta,
      status: mapStatus(r.status),
    }));
  } catch (err) {
    console.warn(`getReconciliation(${id}): API unreachable:`, err);
    return null;
  }
}

async function fetchJson<T>(url: string, init?: RequestInit): Promise<T> {
  const resp = await fetch(url, {
    cache: "no-store",
    ...init,
  });
  if (!resp.ok) {
    throw new Error(`${resp.status} ${resp.statusText} — ${url}`);
  }
  return (await resp.json()) as T;
}

async function fetchHistory(base: string, metricId: string): Promise<TrustHistoryPoint[]> {
  try {
    const raw = await fetchJson<{ runs: RunPayload[] }>(
      `${base}/api/v1/metrics/${metricId}/history?limit=30`,
    );
    return raw.runs
      .map<TrustHistoryPoint>((r) => ({
        date: r.started_at.slice(0, 10),
        score: r.trust_score ?? 0,
        status: mapStatus(r.status),
      }))
      .reverse();
  } catch {
    return [];
  }
}

export async function listMetrics(): Promise<Metric[]> {
  const base = apiBase();
  if (!base) return listFixtureMetrics();
  try {
    const payloads = await fetchJson<MetricPayload[]>(`${base}/api/v1/metrics`);
    return payloads.map((p) => toMetricCard(p, []));
  } catch (err) {
    console.warn("listMetrics: API unreachable, falling back to fixtures:", err);
    return listFixtureMetrics();
  }
}

export async function getMetric(id: string): Promise<Metric | null> {
  const base = apiBase();
  if (!base) return getFixtureMetric(id);
  try {
    const payload = await fetchJson<MetricPayload>(`${base}/api/v1/metrics/${id}`);
    const history = await fetchHistory(base, payload.id);
    // Lineage + reconciliation are best-effort — if either call fails,
    // ``toMetricCard`` falls back to a local stub so the detail page still
    // renders without a network-dependency-shaped hole in it.
    const lineage = await getLineage(payload.id);
    const reconciliation = await getReconciliation(payload.id);
    return toMetricCard(payload, history, lineage, reconciliation);
  } catch (err) {
    console.warn(`getMetric(${id}): API unreachable, falling back to fixture:`, err);
    return getFixtureMetric(id);
  }
}

export async function getEmbedToken(id: string): Promise<string | null> {
  const base = apiBase();
  if (!base) return null;
  try {
    const p = await fetchJson<MetricPayload>(`${base}/api/v1/metrics/${id}`);
    return p.embed_token;
  } catch {
    return null;
  }
}

export function getApiBase(): string | null {
  return apiBase();
}

export interface RunExplanation {
  id: string;
  runId: string;
  hypothesis: string;
  suggestedAction: string;
  modelId: string;
  createdAt: string;
}

interface RunExplanationPayload {
  id: string;
  run_id: string;
  hypothesis: string;
  suggested_action: string;
  model_id: string;
  created_at: string;
}

function mapExplanation(p: RunExplanationPayload): RunExplanation {
  return {
    id: p.id,
    runId: p.run_id,
    hypothesis: p.hypothesis,
    suggestedAction: p.suggested_action,
    modelId: p.model_id,
    createdAt: p.created_at,
  };
}

/**
 * Error thrown when the server responds to ``POST /runs/:id/explain`` with
 * a status we want the UI to handle distinctly (e.g. 500 means "operator
 * hasn't set LITMUS_ANTHROPIC_API_KEY" and we should show a muted
 * "not configured" line instead of a red error banner).
 */
export class ExplainError extends Error {
  readonly statusCode: number;

  constructor(message: string, statusCode: number) {
    super(message);
    this.name = "ExplainError";
    this.statusCode = statusCode;
  }
}

/**
 * Fire the AI explainer for a run. Returns the hypothesis + suggested action.
 * Blocks up to 45s — the server promises 30s + network slack.
 *
 * Throws :class:`ExplainError` for HTTP errors (caller checks ``statusCode``).
 */
export async function explainRun(
  runId: string,
  opts: { regenerate?: boolean } = {},
): Promise<RunExplanation> {
  const base = apiBase();
  if (!base) {
    throw new ExplainError("API not configured", 500);
  }
  const qs = opts.regenerate ? "?regenerate=true" : "";
  const resp = await fetch(`${base}/api/v1/runs/${runId}/explain${qs}`, {
    method: "POST",
    cache: "no-store",
  });
  if (!resp.ok) {
    let detail = `${resp.status} ${resp.statusText}`;
    try {
      const body = await resp.json();
      if (body?.detail) detail = body.detail;
    } catch {
      // ignore — fall back to status text.
    }
    throw new ExplainError(detail, resp.status);
  }
  const payload = (await resp.json()) as RunExplanationPayload;
  return mapExplanation(payload);
}

/**
 * Fetch an already-generated explanation. Returns ``null`` if none exists yet.
 */
export async function getRunExplanation(
  runId: string,
): Promise<RunExplanation | null> {
  const base = apiBase();
  if (!base) return null;
  try {
    const payload = await fetchJson<RunExplanationPayload>(
      `${base}/api/v1/runs/${runId}/explanation`,
    );
    return mapExplanation(payload);
  } catch {
    return null;
  }
}
