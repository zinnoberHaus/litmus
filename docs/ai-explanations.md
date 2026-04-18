# AI-Powered Run Explanations

> **Status:** beta (v0.2). Shipped behind an opt-in extras install and an
> environment-variable gate. Disabled by default.

When a run fails, Litmus can generate a one-paragraph hypothesis about the
most likely root cause plus a short, imperative "next step" for the on-call
engineer. The feature lives entirely on the Litmus server — the CLI and UI
proxy through it so the Anthropic API key, privacy disclosure, and prompt
assembly are in one auditable place.

## Quick start

### 1. Install the `[ai]` extras on the server

```bash
pip install 'litmus-data[server,ai]'
```

The `[ai]` extras only add the [`anthropic`](https://pypi.org/project/anthropic/)
Python SDK. It is intentionally not part of `[server]` — operators who don't
want AI features can skip it.

### 2. Set the API key

```bash
export LITMUS_ANTHROPIC_API_KEY="sk-ant-..."
# or (fallback)
export ANTHROPIC_API_KEY="sk-ant-..."
```

The server reads `LITMUS_ANTHROPIC_API_KEY` first and falls back to the
standard `ANTHROPIC_API_KEY`. If **neither** is set, the feature gracefully
degrades: `POST /api/v1/runs/{id}/explain` returns `500` with
`{"detail": "AI explanations not configured: ..."}`, and the UI renders a
muted "AI explanations not configured on this instance" line instead of
the "Explain this failure" button's loading state.

### 3. Use it

From the CLI, pointing at a running server:

```bash
litmus explain-run <run-uuid> --endpoint https://litmus.example.com
```

From the UI, the metric detail page automatically shows a "Why did this
fail?" panel when the latest run has status `failed` or `error`.

From the API directly:

```http
POST /api/v1/runs/{run_id}/explain
POST /api/v1/runs/{run_id}/explain?regenerate=true
GET  /api/v1/runs/{run_id}/explanation
```

`POST` is idempotent — the first call persists a `RunExplanation` row, and
subsequent calls return the cached row without hitting Anthropic unless you
pass `?regenerate=true`. `GET` returns `404` if no explanation has been
generated yet.

## Model & output

- **Model:** `claude-sonnet-4-6` (pricing: \$3.00 / \$15.00 per 1M input/output tokens).
  Sonnet is fast enough for a synchronous HTTP call (typical 5–15 seconds) and
  cheap enough to run liberally.
- **Output shape (guaranteed by forced tool-use):**
  - `hypothesis` — 2–3 sentences, grounded in the failing check's numbers
    and recent run history.
  - `suggested_action` — 1–2 imperative sentences, starting with a verb.

The server enforces the schema by forcing a single tool call
(`return_run_explanation`) with a fixed JSON schema — the model cannot return
free-form prose, so there is no regex parsing of the response.

## What gets sent to Anthropic

**Read this before enabling the feature in production.** Every
`POST /api/v1/runs/{id}/explain` sends the following payload to Anthropic:

1. **A fixed system prompt** describing the explainer's role and tone.
2. **Metric metadata** — name, slug, description, primary table name.
3. **Trust rules** — the `trust:` block from the metric's `.metric` file,
   rendered as JSON (freshness, null, volume, range, change, duplicate,
   schema-drift, and distribution-shift thresholds).
4. **Current run aggregates** — `run.id`, `status`, `started_at`,
   `trust_score`, `value_sum`, `row_count`.
5. **Current run check results** — for every `CheckResult` row: `rule_type`,
   `status`, `message`, `actual_value`, `threshold_value`.
6. **Recent run history** — up to the last 5 prior runs for this metric
   (`started_at`, `status`, `trust_score`, `value_sum`, `row_count`).

**What is NOT sent:**

- **No warehouse row data.** Litmus never reads individual records from the
  warehouse for the explainer, only the already-aggregated check results.
- **No raw SQL.** Neither the user's custom SQL assertions nor the generated
  check queries are included.
- **No warehouse credentials, API keys, or server secrets.**
- **No data from other metrics** — the prompt is scoped to one metric.

Table names (e.g. `primary_table`) and column names (embedded in trust rules
like `null_rate(customer_id) < 0.1%`) _are_ visible to Anthropic, because the
model needs them to ground its hypothesis. If your table or column names are
themselves sensitive, do not enable this feature.

Anthropic's data handling for API requests is described in their
[privacy policy](https://www.anthropic.com/legal/privacy). For commercial
deployments where you need a signed DPA or a zero-retention guarantee, contact
Anthropic directly — Litmus does not brokered that relationship.

## Disabling the feature

There are three ways to turn it off, each useful in a different scenario:

| Scenario | How |
| --- | --- |
| Self-hosted operator, never wants AI | Don't set `LITMUS_ANTHROPIC_API_KEY`. The route stays up and returns 500 "not configured"; the UI renders the muted fallback line. |
| Operator wants AI off permanently | Install without the `[ai]` extras — `pip install 'litmus-data[server]'`. The route then returns 500 at import time if anyone calls it. |
| Per-metric opt-out | Not yet supported — planned for v0.3. Track the `ai_opt_out` flag RFC in the issue tracker. |

## Scope guardrails

By design, the explainer:

- **Never runs automatically.** Every explanation is triggered by an explicit
  POST — on ingestion, on dashboard view, or on CLI invocation.
- **Never explains passing or warning runs.** Those return `400` with
  `{"detail": "Nothing to explain: run ... has status 'passed'..."}`. This
  prevents users from burning tokens on healthy runs.
- **Does not decide or act.** The `suggested_action` is a recommendation. The
  UI copy ends every explanation with "AI output — verify before acting."
- **Does not run tools or shell commands.** The model is given a single
  structured-output tool and nothing else; it cannot execute code or fetch URLs.

## Troubleshooting

### "AI explanations not configured" in the UI

The server is missing `LITMUS_ANTHROPIC_API_KEY` (and `ANTHROPIC_API_KEY`).
Either set one of those env vars and restart the server, or confirm the
feature is intentionally disabled.

### `POST /explain` returns `400 Nothing to explain`

The run status is `passed` or `warning`. The endpoint intentionally refuses
these — only `failed` and `error` runs are explainable.

### `POST /explain` returns `502 Anthropic API call failed`

The upstream Anthropic API returned an error (rate limit, network, etc.) or
the model returned a malformed response. Retry with `?regenerate=true` after
a short wait. The server logs the full error; check your server logs for
`ExplainError`.

### The hypothesis cites a table I don't have

The model is generalizing from the trust rules. Tighten the `description`
field on the metric — a one-sentence description of the source system
dramatically improves groundedness.

### The explanation feels stale after I re-ran the check

`GET /explanation` returns the cached hypothesis from the first
`POST /explain` call. Force a refresh with
`POST /api/v1/runs/{id}/explain?regenerate=true` — the existing
`RunExplanation` row is updated in place (no duplicates).
