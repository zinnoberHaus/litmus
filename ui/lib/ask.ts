/**
 * Client helper for ``POST /api/v1/ask``.
 *
 * The AI Q&A backend endpoint is being built in parallel (see blueprint
 * task #54). Until it ships, this helper returns a mocked response in dev so
 * the chat UI renders end-to-end. The JSON contract is the minimal shape
 * task #53 and #54 agreed on; any server-side expansion must stay additive.
 *
 * Contract (minimal shape agreed with #54):
 *
 *     POST /api/v1/ask
 *       { question: string, metric_slug?: string, context?: object }
 *     → { answer: string,
 *         metric_slug: string,
 *         metric_name?: string,
 *         metric_url?: string,
 *         value?: number,
 *         trust_status: "passed"|"warning"|"failed"|"error"|"unknown",
 *         definition_url: string,
 *         explanation?: string,
 *         suggestions?: string[] }
 *
 * The server-side implementation described in the blueprint (Decision 4) may
 * return richer fields (e.g. ``run_id``, ``model_id``, ``time_window``). The
 * UI tolerates extra keys and only renders what it knows — forward-compatible
 * by design.
 */

export type AskTrustStatus =
  | "passed"
  | "warning"
  | "failed"
  | "error"
  | "unknown";

export interface AskRequest {
  question: string;
  metric_slug?: string;
  context?: {
    user?: string;
    channel?: string;
    source?: string;
  };
}

export interface AskResponse {
  answer: string;
  metric_slug: string;
  metric_name?: string;
  metric_url?: string;
  value?: number;
  trust_status: AskTrustStatus;
  definition_url: string;
  explanation?: string;
  suggestions?: string[];
  /** Optional — some backends return a run id for follow-up explain calls. */
  run_id?: string;
  /** Optional — e.g. "last_month", "ytd". */
  time_window?: string;
  /** Optional — e.g. "claude-sonnet-4-6". */
  model_id?: string;
}

export interface AskError {
  code: "unresolved" | "metric_not_found" | "warehouse_unavailable" | "ai_not_configured" | "transport";
  message: string;
  suggestions?: string[];
}

function publicApiBase(): string | null {
  if (typeof window === "undefined") {
    return process.env.LITMUS_API_INTERNAL ?? process.env.NEXT_PUBLIC_LITMUS_API ?? null;
  }
  return process.env.NEXT_PUBLIC_LITMUS_API ?? null;
}

/**
 * Mocked response used in dev and when the real ``/api/v1/ask`` endpoint is
 * unavailable. Keeps the UI lively during the #54 build-out. When the real
 * endpoint ships, nothing about the caller changes — ``postAsk`` flips from
 * mock to real automatically based on ``apiBase()``.
 */
function mockAskResponse(req: AskRequest): AskResponse {
  const slug = req.metric_slug ?? "mrr";
  const question = req.question.trim();

  // Cheap intent sniff so the demo feels alive — the real server will do the
  // heavy lifting with Claude.
  const lower = question.toLowerCase();
  let trust: AskTrustStatus = "passed";
  let value = 482_150;
  let metricName = "Monthly Recurring Revenue";
  let resolvedSlug = slug;

  if (lower.includes("churn")) {
    trust = "failed";
    value = 4.2;
    metricName = "Gross Monthly Churn";
    resolvedSlug = "churn";
  } else if (lower.includes("active") || lower.includes("mau") || lower.includes("users")) {
    trust = "warning";
    value = 128_402;
    metricName = "Monthly Active Users";
    resolvedSlug = "mau";
  }

  const answer =
    trust === "passed"
      ? `${metricName} is currently ${fmtValue(value, resolvedSlug)}. All five trust checks passed in the latest run.`
      : trust === "warning"
        ? `${metricName} is ${fmtValue(value, resolvedSlug)} but one check is in warning — cross-source reconciliation shows a ~2% gap with Looker.`
        : `${metricName} is ${fmtValue(value, resolvedSlug)} and the metric is currently failing its trust rules — please confirm before publishing.`;

  return {
    answer,
    metric_slug: resolvedSlug,
    metric_name: metricName,
    metric_url: `/metrics/${resolvedSlug}`,
    value,
    trust_status: trust,
    definition_url: `/metrics/${resolvedSlug}`,
    explanation:
      trust === "passed"
        ? undefined
        : "Hypothesis: an upstream schema change bumped the denominator. Compare the latest run against the previous week.",
    time_window: "last_month",
    model_id: "mock-claude",
  };
}

function fmtValue(value: number, slug: string): string {
  if (slug === "mrr" || slug === "arr" || slug.includes("revenue")) {
    return value.toLocaleString("en-US", {
      style: "currency",
      currency: "USD",
      maximumFractionDigits: 0,
    });
  }
  if (slug === "churn" || slug.includes("rate")) {
    return `${value.toFixed(2)}%`;
  }
  return value.toLocaleString("en-US");
}

/**
 * POST ``/api/v1/ask``. Falls back to a local mock if the API base is unset
 * or the endpoint is not yet deployed, so the UI renders end-to-end even
 * before task #54 ships. The mock path is signposted via a console warning so
 * developers notice they aren't hitting a real backend.
 */
export async function postAsk(req: AskRequest): Promise<AskResponse> {
  const base = publicApiBase();
  if (!base) {
    console.info("[litmus] /ask backend not configured — using mock response");
    await smallDelay();
    return mockAskResponse(req);
  }
  try {
    const resp = await fetch(`${base}/api/v1/ask`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(req),
      cache: "no-store",
    });
    if (resp.status === 404 || resp.status === 501) {
      // Endpoint not implemented yet — transparently fall back to the mock.
      console.info(
        "[litmus] /ask endpoint not implemented yet — using mock response",
      );
      await smallDelay();
      return mockAskResponse(req);
    }
    if (!resp.ok) {
      const detail = await safeDetail(resp);
      throw {
        code: mapErrorCode(resp.status),
        message: detail,
      } satisfies AskError;
    }
    return (await resp.json()) as AskResponse;
  } catch (err) {
    // Any transport failure → fall back to the mock so the panel never shows
    // a broken state in dev. Real-world error handling (403, 422, 503) is
    // handled inside the ``resp.ok`` branch above.
    if (err && typeof err === "object" && "code" in err) {
      throw err;
    }
    console.warn("[litmus] /ask transport error — using mock response", err);
    await smallDelay();
    return mockAskResponse(req);
  }
}

async function safeDetail(resp: Response): Promise<string> {
  try {
    const body = (await resp.json()) as { detail?: string };
    return body.detail ?? `${resp.status} ${resp.statusText}`;
  } catch {
    return `${resp.status} ${resp.statusText}`;
  }
}

function mapErrorCode(status: number): AskError["code"] {
  if (status === 404) return "metric_not_found";
  if (status === 422) return "unresolved";
  if (status === 503) return "warehouse_unavailable";
  if (status === 500) return "ai_not_configured";
  return "transport";
}

function smallDelay(): Promise<void> {
  // Feels more natural than an instant reply; not a rate limit.
  return new Promise((resolve) => setTimeout(resolve, 400));
}
