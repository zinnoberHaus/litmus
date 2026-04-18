# AI Q&A — `POST /api/v1/ask`

Ask a business question in plain English, get a number with a trust stamp and
a link back to the metric definition. This is the PM-facing surface per
`REFACTOR_BLUEPRINT.md` §2.4 (task #54).

Two entry points share one engine:

- `POST /api/v1/ask` — invoked by the UI `<AskPanel>` (`ui/lib/ask.ts`) and by
  CLI integrations.
- `POST /api/v1/slack/events` — the `app_mention` handler that turns
  `@litmus what was revenue last month?` into a threaded Slack reply.

## Privacy disclosure

Every AI feature in Litmus is opt-in per install and discloses exactly what
leaves your server. The `ask` engine is no exception.

### What is sent to Claude

The intent-resolution prompt contains:

- **Metric catalog entries** — for each metric in your catalog: `slug`,
  `name`, `description`, `primary_table`, `owner_email`.
- **The user's question** — verbatim.
- **The enumerated `time_window` options** — a closed enum the model must pick
  from (`current_period`, `last_period`, `last_7_days`, `last_30_days`,
  `last_quarter`, `last_year`, `all_time`).

### What is NEVER sent to Claude

- **Warehouse row data.** Ever. Period. The model does not see the rows it's
  summarizing.
- **The computed value.** We run the SQL *after* the model resolves the
  intent. The model never sees `SUM(amount)` results.
- **The generated SQL.** Claude does not generate SQL, and Claude does not see
  the SQL we generate.
- **API keys, warehouse credentials, or user identity.**
- **Spec text or trust rules** — the catalog snapshot is limited to the five
  fields listed above.
- **Other orgs' data.** v0.3 is single-tenant but the query is scoped to the
  acting org anyway.

### Why this split matters

Claude gates *intent* (which metric, which time window). The server owns
*execution* (SQL templating, warehouse query, answer formatting). Even a
fully compromised model API key cannot exfiltrate warehouse data — the SQL
is generated server-side from the stored `MetricSpec` and runs against the
connector you configured in `litmus.yml`.

This is the same bright line the blueprint draws in Decision 4.

## How it answers

```
┌─────────────────┐  question    ┌────────────────────┐
│  Caller (UI,    │─────────────▶│  POST /api/v1/ask  │
│  Slack mention) │              └──────────┬─────────┘
└─────────────────┘                         │
                                            ▼
                                ┌───────────────────────────┐
                                │ 1. Intent resolution      │
                                │    (Claude, forced tool)  │
                                └──────────┬────────────────┘
                                            │ {metric_slug, time_window}
                                            ▼
                                ┌───────────────────────────┐
                                │ 2. SQL templating         │
                                │    (MetricSpec, server)   │
                                └──────────┬────────────────┘
                                            │ SELECT SUM(...) FROM ... WHERE ...
                                            ▼
                                ┌───────────────────────────┐
                                │ 3. Warehouse execution    │
                                │    (BaseConnector)        │
                                └──────────┬────────────────┘
                                            │ value
                                            ▼
                                ┌───────────────────────────┐
                                │ 4. Trust lookup           │
                                │    (latest Run.status)    │
                                └──────────┬────────────────┘
                                            │ trust_status
                                            ▼
                                ┌───────────────────────────┐
                                │ 5. Template an answer     │
                                │    (no second LLM call)   │
                                └──────────┬────────────────┘
                                            │
                                            ▼
                                     AskOut (JSON)
```

## Setup

AI Q&A ships behind the `[ai]` extras — the same gate as
`POST /api/v1/runs/{id}/explain`.

```bash
pip install litmus-data[ai]
export LITMUS_ANTHROPIC_API_KEY=sk-ant-...
# or: export ANTHROPIC_API_KEY=sk-ant-...
```

If the key is unset, the engine raises and the route responds:

```json
HTTP/1.1 500 Internal Server Error
{"detail": "AI Q&A is not configured. Set LITMUS_ANTHROPIC_API_KEY or install 'litmus-data[ai]'."}
```

The Slack `app_mention` handler catches the same error and posts a friendly
`"AI answers aren't configured on this server"` reply instead of failing
silently.

## Request / response contract

Shapes are authored in `ui/lib/ask.ts`. If the server changes the contract,
update that file in the same PR.

**Request:**

```json
POST /api/v1/ask
{
  "question": "what was revenue last month?",
  "metric_slug": "revenue",
  "context": {"user": "alice@example.com", "channel": "#data-pulse"}
}
```

- `question` (required) — the user's natural-language question, verbatim.
- `metric_slug` (optional) — when set, the engine skips Claude and goes
  straight to SQL templating against this metric. Use this from the
  metric-detail-page `<AskPanel>` where the metric is already resolved.
- `context` (optional) — reserved for v0.4 personalization; not sent to
  Claude today.

**Response:**

```json
{
  "answer": "Monthly Revenue for the last period was 4,218,430. Trust is green — all checks passed on the latest run.",
  "metric_slug": "revenue",
  "metric_name": "Monthly Revenue",
  "metric_url": "https://litmus.example.com/metrics/revenue",
  "value": 4218430.12,
  "trust_status": "passed",
  "definition_url": "https://litmus.example.com/metrics/revenue",
  "explanation": null,
  "run_id": "a4c…",
  "time_window": "last_period",
  "model_id": "claude-sonnet-4-6"
}
```

`trust_status` is always one of: `passed` | `warning` | `failed` | `error` | `unknown`.

## Error envelope

| Status | Code | When |
|---|---|---|
| 400 | `bad_input` | Empty question, or spec has no Source table. |
| 404 | `metric_not_found` | Caller passed an unknown `metric_slug`. |
| 422 | `unresolved` | Claude's confidence was < 0.5. Body includes top-3 `suggestions` for UI chips. |
| 500 | `ai_not_configured` | `LITMUS_ANTHROPIC_API_KEY` unset / `[ai]` extra not installed. |
| 502 | `ai_transport` | Anthropic SDK raised after we reached the API. |
| 503 | `warehouse_unavailable` | The templated SQL failed against the warehouse. |

## Manual verification

Out-of-session verification for operators without an Anthropic key in their
local sandbox:

1. Set the key in your shell:
   ```bash
   export LITMUS_ANTHROPIC_API_KEY=sk-ant-...
   ```
2. Start the server:
   ```bash
   uvicorn litmus_api.main:app --port 8080
   ```
3. Seed a metric and a run (or wait for your CI to push one).
4. POST a sample request:
   ```bash
   curl -X POST http://localhost:8080/api/v1/ask \
     -H 'Content-Type: application/json' \
     -d '{"question": "what was revenue last month?"}'
   ```
5. Expect a JSON body with `trust_status` mirroring the latest run and a
   non-null `answer` string.

## Limits

- **Single scalar answer per question.** Group-by / multi-dimensional queries
  are v0.4 (the `filters` tool field is reserved but ignored in v0.3).
- **Stateless.** Each request is independent — no conversation memory. v0.4
  may add a `context.thread_id` for multi-turn.
- **Read-only by convention.** The engine only issues `SELECT`. The connector
  you configure in `litmus.yml` must be a read-only role for this guarantee
  to hold at the warehouse layer.
- **Never generates SQL through Claude.** The intent resolver is forced into
  a tool call that returns a `metric_slug` + enum `time_window`; SQL comes
  from the stored `MetricSpec`.
