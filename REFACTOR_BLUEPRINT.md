# Litmus v0.3 — Refactor Blueprint

> **Status:** North-star architecture doc for the v0.3 pivot. Every specialist
> (`litmus-advocate`, `litmus-connector`, `litmus-inspector`, `litmus-ui`)
> reads this first and treats it as the source of truth for scope, file
> boundaries, and cross-package handoff.
>
> **Author:** Architect. **Date:** 2026-04-18. **Targets:** Tasks #50–#56.

---

## 0. TL;DR

v0.3 repositions Litmus from "BDD for metrics" to:

> **Canonical metric contracts for engineers, AI-answered questions for PMs,
> embeddable trust badges for everyone.**

Three surfaces, three audiences, one underlying `MetricSpec`. We ship:

1. A **`dbt_packages/litmus/`** package (Elementary pattern) that runs trust
   checks as an `on-run-end` hook and materialises results to warehouse tables.
2. A **Slack sign-off + `/ask` bot** that turns metric revisions into approve/reject
   flows and NL questions into warehouse-backed answers.
3. A **redesigned UI** with a three-audience landing page, dbt-first install
   flow, and an AI chat panel on every metric detail page.
4. **Badge distribution polish** so the embed SVG renders cleanly in Notion,
   Slack, Confluence, and README files — every rendered badge is a backlink.

No `.metric` grammar changes. No `MetricSpec` breaking changes. No new JSON
schema version unless forced. No Cloud / multi-tenant / SSO / billing work.

---

## 1. Positioning

### 1.1 One-liner

> **Litmus is the trust-and-approval layer for business metrics.** Engineers
> define metrics as code (DSL or YAML). PMs ask questions and sign off on
> definitions in Slack. Everyone sees a live trust badge — in the README, in
> Notion, in the deck.

### 1.2 Three audiences, three surfaces

```
┌─────────────────────┬──────────────────────────┬──────────────────────────┐
│    ENGINEERS        │         PMs              │        EVERYONE          │
├─────────────────────┼──────────────────────────┼──────────────────────────┤
│ .metric / YAML      │ Slack /ask <question>    │ Live trust badge SVG     │
│ dbt package         │ Slack sign-off on        │ embedded in Notion,      │
│ CLI, CI, GitHub     │    metric revisions      │ Slack, Confluence,       │
│ Action              │ AI Q&A with provenance   │ README, GitHub Pages     │
│                     │ No SQL, no YAML, no git  │                          │
├─────────────────────┼──────────────────────────┼──────────────────────────┤
│ "My tests pass."    │ "Revenue is $4.2M, and   │ "The badge says green,   │
│                     │  it's green."            │  I believe the number."  │
└─────────────────────┴──────────────────────────┴──────────────────────────┘
         ▲                        ▲                        ▲
         │                        │                        │
         └────────────── shared MetricSpec ────────────────┘
```

Engineers are the **adoption vector**. PMs and execs are the **retention**
engine. The badge is the **viral loop**. Any feature that strengthens one
surface without weakening the other two passes the bar; anything else does not.

### 1.3 Competitive map

| Vendor / layer | What they own | Litmus relationship |
|---|---|---|
| **dbt** (transformation) | SQL models, `schema.yml`, `not_null` tests | **Complement.** We ship as a dbt package. We consume dbt's tests as trust rules. We never re-implement `not_null`. |
| **dbt Semantic Layer / MetricFlow** | Metric definitions as YAML, MDX serving | **Complement.** Semantic layer says *how* revenue is computed. Litmus says *is it trustworthy right now* + *did the business sign off on the definition*. We can import MetricFlow YAML via the same parser path as `.metric`. |
| **Cube.dev** | Headless BI semantic layer | **Complement.** Same story as dbt SL — we are not a serving layer. |
| **Elementary** | dbt-first data observability (test history, alerts) | **Primary reference.** Elementary is the playbook. Their dbt package materialises results to warehouse tables and `edr` reads them back. We copy the pattern (see Decision 2) and differentiate by adding the PM + badge + AI layer *above* Elementary's engineer-only surface. |
| **Monte Carlo / Metaplane / Bigeye** | Full-stack data observability, anomaly detection, lineage | **Overlap, but different ICP.** These are expensive platforms for enterprise data teams. Litmus is the OSS + PLG wedge — engineers adopt without procurement, PMs get Slack sign-off, business users get the badge. We deliberately don't compete on ML anomaly detection. |
| **Atlan / Collibra / Alation** | Data catalog with governance | **Overlap on metric catalog, not governance.** We ship a lightweight catalog with specs + revisions + badges. We do not ship stewardship workflows, business glossary, or PII tagging. |
| **DataFold / Recce** | dbt diff / data diff | **Adjacent.** They catch SQL-level regressions pre-merge. We catch definition + value-level drift at any time. Compatible stacks. |
| **Looker / Tableau / Mode** | BI serving | **Reconciliation target.** We already reconcile their values against the warehouse (`[bi]` extras). v0.3 adds nothing here. |

**Where Litmus is defensible:**

- The `.metric` DSL is memorable and PM-readable. Even if YAML becomes primary
  (Decision 1), the DSL stays as the documentation surface PMs approve in Slack.
- The **badge** is genuinely novel: no competitor ships a self-hosted
  embeddable trust SVG. Every embed is a free backlink.
- **Three-audience positioning** — nobody else pitches PMs directly. Monte Carlo
  sells to VP Data Eng. Elementary sells to analytics engineers. Atlan sells
  to the Chief Data Officer. Nobody asks the PM "want your revenue question
  answered in Slack with a trust stamp?"

---

## 2. Five strategic decisions

### 2.1 Decision 1: DSL vs YAML → **Both as equal peers**

**Choice:** **(c) — Both equal peers.** YAML is additive; `.metric` DSL stays as
a first-class citizen. A single parser entrypoint dispatches on file extension.

**Why:**

- **DSL stays because:** the Gherkin shape is literally how a PM or finance
  analyst reads a contract ("Given … When … Then … Trust:"). It's the hook
  that makes the Slack sign-off flow legible. YAML doesn't read like English.
- **YAML is added because:** (1) engineers coming from dbt/Cube/MetricFlow
  have YAML muscle memory; (2) LLMs and codegen tools emit YAML reliably but
  stumble on bespoke DSLs; (3) dbt hub submission expects a YAML-native story;
  (4) the MCP endpoint (§4.3) is far cleaner against YAML-structured input.
- **Not "YAML primary":** forcing existing `.metric` users onto YAML breaks the
  PLG wedge. The DSL has been shipped, blogged, and used — demoting it to
  "sugar" is a breaking change in optics even if the parser accepts both.

**README leads with:** the `.metric` DSL in the hero (memorability wins the
scroll), followed by an "or YAML, if you prefer" toggled tab. The docs index
treats them as peers with cross-links.

**Architectural implications:**

- `litmus/parser/yaml_parser.py` (new) — thin loader from YAML dict →
  `MetricSpec`. Reuses the same AST-to-spec lowering code as the DSL.
- `litmus/parser/__init__.py` grows a single dispatcher:
  ```python
  def parse_metric_file(path: str | Path) -> MetricSpec:
      ext = Path(path).suffix.lower()
      if ext in {".yml", ".yaml"}:
          return parse_metric_yaml(path)
      return parse_metric_dsl(path)  # existing .metric path
  ```
- `MetricSpec` is unchanged. Both paths produce the same dataclass.
- CLI auto-detects — `litmus check metrics/` picks up `*.metric`, `*.yml`,
  and `*.yaml` under `metrics/`.
- `docs/spec-language.md` gets a companion `docs/spec-yaml.md` with a
  side-by-side reference table.

**What NOT to do:** the YAML path MUST NOT gain features the DSL lacks. If YAML
learns a new key, the DSL learns the same syntax in the same PR. One spec
model, two surfaces — otherwise we have two products.

### 2.2 Decision 2: dbt package shape → **Elementary pattern, warehouse backend opt-in via `--backend`**

**Choice:** Ship `dbt_packages/litmus/` (also submitted to dbt Hub as
`litmus-data/litmus`) that materialises trust check results to the warehouse
via an `on-run-end` hook. The Python CLI gains a `--backend {sqlite,warehouse,auto}`
flag; **default is `auto`** (detect from `litmus.yml` + env).

**Detection rules for `auto`:**

1. If `dbt_project.yml` exists in cwd or ancestor AND the dbt profile matches
   `litmus.yml`'s warehouse → `warehouse`.
2. Else if `$LITMUS_BACKEND=warehouse` → `warehouse`.
3. Else → `sqlite` (existing `~/.litmus/history.db` behavior).

This preserves the zero-config first-run experience for solo engineers while
letting teams with shared dbt projects adopt the warehouse backend by just
installing the package — no flag required.

**Warehouse schema (proposed; Connector owns final SQL per dialect):**

```sql
-- Canonical name: {{ target.schema }}_litmus.litmus_runs
-- (Elementary uses {schema}_elementary — we mirror the prefix pattern.)
CREATE TABLE litmus_runs (
    id                  VARCHAR(36) NOT NULL,       -- UUID
    metric_slug         VARCHAR(200) NOT NULL,
    metric_name         VARCHAR(500) NOT NULL,
    status              VARCHAR(16) NOT NULL,       -- passed|warning|failed|error
    trust_score         DECIMAL(5,4),
    started_at          TIMESTAMP NOT NULL,
    finished_at         TIMESTAMP,
    commit_sha          VARCHAR(64),
    ci_run_id           VARCHAR(64),
    triggered_by        VARCHAR(32) NOT NULL,       -- dbt | cli | scheduled
    value_sum           DECIMAL(38,6),
    row_count           BIGINT,
    schema_fingerprint  VARCHAR(128),
    column_means_json   VARCHAR(16000),             -- stringified JSON; safer across dialects
    spec_json           VARCHAR(16000),
    PRIMARY KEY (id)
);

CREATE TABLE litmus_check_results (
    id                  VARCHAR(36) NOT NULL,
    run_id              VARCHAR(36) NOT NULL,
    rule_type           VARCHAR(32) NOT NULL,
    rule_json           VARCHAR(4000) NOT NULL,
    status              VARCHAR(16) NOT NULL,
    message             VARCHAR(2000),
    actual_value        DECIMAL(38,6),
    threshold_value     DECIMAL(38,6),
    duration_ms         INTEGER,
    PRIMARY KEY (id)
);

-- Soft index on (metric_slug, started_at DESC) — we issue it post-create since
-- dbt's adapter abstractions don't uniformly support CREATE INDEX.
```

Column types mirror the Postgres catalog tables in `litmus_api/models/` as
closely as the dbt adapter layer allows. `VARCHAR` rather than `TEXT`/`JSONB`
to keep BigQuery + Snowflake + Postgres + DuckDB all happy with the same DDL.
Large JSON blobs (`spec_json`, `column_means_json`) are stringified — we pay a
parse cost on read but the schema ships without adapter-specific branching.

**`dbt_packages/litmus/` layout:**

```
dbt_packages/litmus/
├── dbt_project.yml
├── README.md
├── packages.yml                     # transitive deps (none expected for v0.3)
├── macros/
│   ├── litmus_run_trust_checks.sql  # entry macro, called from on-run-end
│   ├── get_trust_check_rules.sql    # introspects model meta / .metric / YAML
│   ├── materialize_run.sql          # INSERT into litmus_runs
│   ├── materialize_results.sql      # INSERT into litmus_check_results
│   └── adapters/
│       ├── default.sql
│       ├── snowflake.sql
│       ├── bigquery.sql
│       ├── postgres.sql
│       └── duckdb.sql
├── models/
│   ├── litmus_runs.sql              # staging incremental wrapper (optional)
│   └── litmus_check_results.sql
└── tests/
    └── fixtures/                    # dbt integration tests
```

**How it ties into existing code:**

- `dbt_packages/litmus/macros/litmus_run_trust_checks.sql` shells out to the
  Python `litmus` CLI via a generic macro — this is the pragmatic path that
  Elementary uses for its heavier analytics (they call `edr` from `on-run-end`).
  For pure-SQL rules (freshness, null rate, row count) the macros render SQL
  directly; for rules that need the `HistoryStore` semantics (change,
  distribution shift), the macro emits a Python call that reads/writes the
  warehouse tables.
- `litmus/checks/history.py` grows a `WarehouseHistoryStore` sibling to the
  existing `SqliteHistoryStore`; both implement the same interface. The CLI
  picks one based on `--backend`. Nothing else in `checks/` changes.

**dbt Hub submission — `packages.yml` snippet users write:**

```yaml
packages:
  - package: litmus-data/litmus
    version: [">=0.3.0", "<0.4.0"]
```

Submission format: a PR to `dbt-labs/hub.getdbt.com` with a `data/` directory
entry pointing at our GitHub releases. We create a `dbt-hub` release tag on
every minor version.

### 2.3 Decision 3: Slack surface → **Hybrid (webhook for MVP, Events API route scaffolded)**

**Choice:** **Hybrid.** v0.3 ships with **webhook-only** posting for sign-off
notifications and slash-command handling, PLUS scaffolds the `/api/v1/slack/events`
route and signature verification so a full Slack App can be upgraded to in v0.4
without changing the data model. No Slack Marketplace distribution in v0.3.

**Why webhook-only for MVP:**

- Slack App distribution requires a public OAuth redirect, a privacy policy,
  a `manifest.yml`, a reviewed Slack App, and a deployment we don't run
  centrally. That's 4–6 weeks of Slack-specific work that blocks the rest of
  v0.3.
- Webhook + slash-command URLs gives users 90% of the UX with ~1 day of impl:
  they paste a webhook URL into our server config, and create a Slack app
  in *their* workspace with two slash commands pointed at our HTTPS endpoints.
- Events-API scaffolding means v0.4 Slack-App upgrade is additive, not a rewrite.

**New env vars:**

```
LITMUS_SLACK_WEBHOOK_URL        # outbound: where sign-off prompts + run
                                #   failure notifications POST to
LITMUS_SLACK_SIGNING_SECRET     # inbound:  HMAC secret for slash commands
                                #   and Events API (Slack's own signature)
LITMUS_SLACK_BOT_USER_AGENT     # optional: custom UA for the outbound POST
```

All three are optional. If `LITMUS_SLACK_WEBHOOK_URL` is unset, the server
logs "Slack not configured" and the sign-off feature is silently disabled —
never crashes the API.

**New endpoints (all under `/api/v1/slack/`):**

```
POST /api/v1/slack/events          # Events API callback (scaffolded; v0.4 fills in)
POST /api/v1/slack/commands        # slash commands: /ask, /litmus approve, /litmus reject
POST /api/v1/slack/interactions    # button clicks from block-kit messages
POST /api/v1/slack/signoff         # internal: triggers an outbound signoff prompt
                                   #   (called by the MetricRevision write path)
```

Signature verification on every inbound request: check `X-Slack-Signature`
and `X-Slack-Request-Timestamp` against `LITMUS_SLACK_SIGNING_SECRET`,
reject if older than 5 minutes (Slack's spec). Returns 401 on mismatch —
**never silently accepts**, following the GitHub webhook pattern already in
`litmus_api/routes/webhooks.py`.

**New DB columns on `MetricRevision` (Alembic migration 0006):**

```python
signoff_status      = Column(String(16), nullable=True)  # pending|approved|rejected|null
signoff_requested_by = Column(String(320), nullable=True)
signoff_requested_at = Column(DateTime, nullable=True)
signoff_actor       = Column(String(320), nullable=True)  # email or slack user id
signoff_at          = Column(DateTime, nullable=True)
signoff_comment     = Column(Text, nullable=True)
slack_message_ts    = Column(String(32), nullable=True)   # ts of the prompt message
```

`signoff_status=NULL` means "sign-off not required / legacy revision" — does
not break existing revisions. The upsert path only sets `pending` when the
org has `LITMUS_SLACK_WEBHOOK_URL` configured AND the metric's spec has a
`signoff_required: true` flag in the (YAML-only) header. DSL users who don't
want sign-off get no behavior change.

**UX flow:**

1. Engineer pushes `.metric` change → GitHub webhook → `_perform_upsert` creates
   new `MetricRevision` → if sign-off required, POST to `LITMUS_SLACK_WEBHOOK_URL`
   with a Block Kit message showing spec diff + "Approve" / "Reject" buttons.
2. PM clicks a button → Slack POSTs to `/api/v1/slack/interactions` → we
   verify the signature, update `MetricRevision.signoff_status`, and reply
   to Slack with a confirmation.
3. UI metric-detail page shows the sign-off chip next to the revision entry.

### 2.4 Decision 4: AI Q&A architecture → **Run SQL directly against a read-only connection, Claude-gated for intent**

**Choice:** New module `litmus_api/ai/ask.py`. Claude Sonnet 4.6 with forced
tool-use resolves the user's question into `{metric_slug, time_window, filters}`,
the server generates SQL from the `MetricSpec`, runs it against the warehouse's
**read-only** connector, and returns `{value, trust_status, metric_url,
explanation}`. Claude never sees warehouse rows.

**Why run SQL directly (not "emit for a human"):**

- The PM surface is worth nothing if the answer requires copy-pasting SQL.
- The `MetricSpec` already has everything needed to build the query
  (`sources`, `conditions`, `calculations`). `litmus/generators/sql_generator.py`
  exists — we extend it, don't rewrite.
- Safety comes from (a) SQL is templated from the spec, not from Claude's
  output; (b) the connector is gated behind a read-only flag; (c) the
  time-window arg from Claude is validated against a whitelist (`last_7_days`,
  `last_month`, `current_month`, `ytd`, …).

**Tool schema Claude is forced into:**

```json
{
  "name": "resolve_metric_question",
  "input_schema": {
    "type": "object",
    "properties": {
      "metric_slug": {
        "type": "string",
        "description": "The slug of the catalog metric that best answers the question. Must match an entry from the provided metric list exactly."
      },
      "time_window": {
        "type": "string",
        "enum": [
          "current_day", "yesterday", "last_7_days",
          "current_week", "last_week",
          "current_month", "last_month", "mtd",
          "current_quarter", "last_quarter", "qtd",
          "current_year", "last_year", "ytd",
          "all_time"
        ]
      },
      "filters": {
        "type": "array",
        "items": {
          "type": "object",
          "properties": {
            "column": {"type": "string"},
            "op": {"type": "string", "enum": ["=", "!=", ">", "<", ">=", "<=", "in"]},
            "value": {"type": ["string", "number", "boolean", "array"]}
          },
          "required": ["column", "op", "value"]
        }
      },
      "confidence": {"type": "number", "minimum": 0, "maximum": 1},
      "unresolved_reason": {
        "type": "string",
        "description": "If the question cannot be resolved to a metric, explain why in one sentence. Null if resolved."
      }
    },
    "required": ["confidence"]
  }
}
```

**Privacy disclosure (what goes into Claude's prompt):**

- Metric catalog: `slug`, `name`, `description`, `primary_table`, `tags`.
- For the top candidate only: the `MetricSpec.trust` rules.
- The user's question, verbatim.
- Last 5 runs' **aggregates** (`trust_score`, `status`, `value_sum`, `row_count`).

Explicitly NEVER sent:
- Raw warehouse row data.
- The generated SQL.
- Warehouse credentials.
- Other orgs' metrics (single-tenant today; tenancy-scoped later).

This mirrors `docs/ai-explanations.md` section by section. We update that doc
with a parallel disclosure for `/ask`.

**Endpoints:**

```
POST /api/v1/ask                # public UI chat panel + CLI entry point
POST /api/v1/slack/commands     # Slack /ask <question> dispatches here internally
```

Request body:
```json
{
  "question": "what was revenue last month?",
  "context": {"user": "alice@example.com", "channel": "#data-pulse"}
}
```

Response body:
```json
{
  "metric": {"slug": "monthly_revenue", "name": "Monthly Revenue", "url": "/metrics/monthly_revenue"},
  "time_window": "last_month",
  "value": 4218430.12,
  "trust": {"status": "passed", "score": 0.95, "run_id": "…"},
  "answer": "Monthly Revenue for March 2026 was $4.22M. Trust is green (all 5 checks passed in the 03-31 run).",
  "model_id": "claude-sonnet-4-6"
}
```

**Error contract:**

- 422 `unresolved`: Claude's `confidence < 0.5` OR `unresolved_reason` is set.
  Response includes `suggestions: string[]` — the top 3 metric slugs Claude
  considered. UI renders these as clickable chips.
- 404 `metric_not_found`: Claude returned a slug that doesn't exist.
- 503 `warehouse_unavailable`: the generated SQL failed to execute. Response
  includes the last-known value from the latest `Run.value_sum`, clearly
  labeled as stale with a timestamp.
- 500 `ai_not_configured`: `LITMUS_ANTHROPIC_API_KEY` missing. Same fallback
  as `/explain`.

**SQL generation:**

`litmus/generators/sql_generator.py` already builds the headline-value query.
We add `build_ask_query(spec, time_window, filters) -> str` which:
- Resolves `time_window` to a `WHERE` clause on the spec's declared timestamp
  column (default `updated_at`, overridable in the spec header).
- Appends filter predicates (each validated against the spec's `sources` columns).
- Returns a single aggregation identical to what `run_checks` would compute.

Claude never sees this SQL. It is fully templated from the spec and validated
args.

### 2.5 Decision 5: UI information architecture

**Choice:** One marketing-style landing page at `/` with three scroll
sections (Engineers / PMs / Viewers), dedicated onboarding flows under
`/install`, and the AI chat panel lives **both** as a sidebar on every
`/metrics/[slug]` page AND as a standalone `/ask` page for direct linking.

**Sitemap:**

```
/                                   Landing — three-audience split
├── /install                        Install flow hub
│   ├── /install/dbt                dbt package (primary)
│   ├── /install/cli                standalone CLI (secondary)
│   └── /install/hosted             hosted catalog (tertiary)
├── /docs                           Redirect to docs/ on GitHub
├── /metrics                        Catalog (existing; minor polish)
│   └── /metrics/[slug]             Metric detail (AI chat sidebar added)
│       ├── ?tab=revisions          Existing
│       ├── ?tab=lineage            Existing
│       ├── ?tab=reconciliation     Existing
│       └── ?tab=history            Existing
├── /ask                            Standalone AI chat page
├── /badge                          Badge gallery + copy-paste snippets
├── /embed/[token]                  Existing SVG + card proxies
└── /login                          Placeholder for v0.4 (OSS stays single-tenant)
```

**Nav chrome:**

Top nav: logo, "Metrics", "Ask", "Badges", "Install", "Docs" (external link,
opens in same tab to the docs/ folder on GitHub). Right-side: org switcher
is **hidden in OSS** (single org only); replaced by a "Powered by Litmus"
attribution link so the nav weight matches the three-column hero. Login
button is a stub that shows a "v0.4 — hosted Cloud coming soon" toast.

**Landing `/` structure (one page, three sections):**

```
HERO  — "Canonical metric contracts for engineers, AI-answered questions
         for PMs, embeddable trust badges for everyone."
         Live badge demo (auto-polling a public demo metric).
         CTA: "Install in dbt" / "Try the CLI" / "See it live" (chat demo)

SECTION 1 — FOR ENGINEERS
  dbt package code snippet, DSL vs YAML toggle, Trust rules list,
  link to /install/dbt

SECTION 2 — FOR PMs
  Slack screenshot (approve/reject), /ask GIF,
  link to /install (Slack setup inside Install > Slack)

SECTION 3 — FOR EVERYONE
  Badge gallery: Notion, Slack unfurl, README,
  Confluence. Live copy-paste snippets. Link to /badge.

SOCIAL PROOF  — GitHub stars, PyPI downloads, Coalesce logo (once submitted),
                user logos (empty for v0.3 — placeholder grid that we fill
                post-launch)

FOOTER
```

**Install flow `/install`:**

Three tab cards, dbt first. Each tab is a step-by-step with copy buttons,
"next step" nav, and a "it worked" checkbox that flips a section header
on the next page (so users know they're on the right track). The hosted
path ends at "run `docker-compose up` and visit `localhost:3000`".

**AI chat panel:**

- On `/metrics/[slug]`: right-side collapsible panel, 380px wide on desktop,
  full bottom sheet on mobile. Input "Ask about this metric…" pre-seeds
  `context.metric_slug`. Empty state shows 3 pre-filled example questions
  from the metric's spec.
- On `/ask`: full-width centred chat. No pre-seeded metric. Has a
  left-side metric picker for scoping.
- Both share the same `<AskPanel>` component and POST to `/api/v1/ask`.

---

## 3. File-by-file change map

Each subsection is scoped to one task package. Specialists claim tasks in
order; cross-package dependencies are called out at the end.

### 3.1 Task #50 — Docs / positioning refresh (owner: `litmus-advocate`)

**Files to CREATE:**

| Path | Purpose |
|---|---|
| `docs/positioning.md` | Canonical 3-audience pitch, competitive map, elevator pitches for each audience. Source of truth for all public copy. |
| `docs/spec-yaml.md` | YAML spec reference, side-by-side with the DSL. |
| `docs/install/dbt.md` | dbt package install walkthrough (engineer home). |
| `docs/install/cli.md` | Standalone CLI walkthrough. |
| `docs/install/slack.md` | Slack sign-off + `/ask` setup. Webhooks-only, step-by-step. |
| `docs/install/hosted.md` | Self-host the FastAPI + Next.js stack via docker-compose. |
| `docs/badges.md` | Badge embedding guide for Notion, Slack, Confluence, README, GitHub Pages. |
| `docs/ai-ask.md` | `/ask` disclosure doc (parallels `docs/ai-explanations.md`). |
| `examples/metrics/monthly_revenue.yml` | YAML twin of an existing `.metric` — demonstrates parity. |

**Files to MODIFY:**

| Path | Change |
|---|---|
| `README.md` | Rewrite hero to the three-audience one-liner. Move `.metric` example below the hero. Add "PM Slack" + "Badge" sections. Keep the full CLI command table but reorder: install → badge → CLI. |
| `CLAUDE.md` | Update the "Project" paragraph to the new positioning. Add YAML to the "pipeline" summary. Add Slack + `/ask` to the "checks → reporters → …" flow in section 1. |
| `docs/ARCHITECTURE.md` | Add a "v0.3 additions" section: dbt package, Slack routes, `/api/v1/ask`, YAML parser. Do NOT rewrite the v0.2 sections — they remain reference for Cloud. |
| `docs/spec-language.md` | Add a callout at the top linking to `docs/spec-yaml.md`. Otherwise unchanged. |
| `docs/getting-started.md` | Split into "Engineer path" / "PM path" / "Badge path" sub-flows. Lead with the dbt install. |
| `docs/examples/saas-metrics/*.metric` | Add `.yml` peer for one example. |
| `CHANGELOG.md` | v0.3 section stub (Advocate owns wording; Architect veto rights on positioning). |
| `litmus/cli.py` | Update `--help` strings on every subcommand to drop BDD-forward language. The command surface itself doesn't change. |
| `action.yml` (description field only) | Reword the action description to match positioning. **Inputs/outputs/contract unchanged.** |
| `examples/README.md` | Add a "DSL vs YAML" section. |

**Files to DELETE / DEPRECATE:**

- Nothing deleted. `docs/DAGSTER_MODEL.md` stays as internal reference.
- The phrase "BDD for metrics" is deprecated in user-facing copy but
  survives as a grep-able phrase inside `docs/DAGSTER_MODEL.md` for history.

**Cross-package dependencies:** Task #50 blocks on nothing. Other tasks
consume its copy: #53 (UI) imports hero + section copy from
`docs/positioning.md`; #51 (dbt package README) links into `docs/install/dbt.md`.

---

### 3.2 Task #51 — dbt package (owner: `litmus-connector`)

**Files to CREATE:**

| Path | Purpose |
|---|---|
| `dbt_packages/litmus/dbt_project.yml` | Minimal project file; name `litmus`, version from Python package. |
| `dbt_packages/litmus/README.md` | Hub-facing install + usage. |
| `dbt_packages/litmus/macros/litmus_run_trust_checks.sql` | `on-run-end` entry point. |
| `dbt_packages/litmus/macros/get_trust_check_rules.sql` | Pull rules from `.metric` files OR from `schema.yml meta: litmus:` blocks. |
| `dbt_packages/litmus/macros/materialize_run.sql` | Insert into `litmus_runs`. |
| `dbt_packages/litmus/macros/materialize_results.sql` | Insert into `litmus_check_results`. |
| `dbt_packages/litmus/macros/ensure_schema.sql` | Idempotent `CREATE TABLE IF NOT EXISTS`. |
| `dbt_packages/litmus/macros/adapters/{default,snowflake,bigquery,postgres,duckdb}.sql` | Per-adapter type mappings. |
| `dbt_packages/litmus/models/litmus_runs.sql` | (Optional) incremental wrapper for users who want dbt to own the state. |
| `dbt_packages/litmus/models/litmus_check_results.sql` | Same. |
| `dbt_packages/litmus/tests/fixtures/dbt_project/` | Integration test fixture. |
| `litmus/checks/history_warehouse.py` | `WarehouseHistoryStore` implementing same interface as `SqliteHistoryStore`. Accepts a `BaseConnector`. |
| `tests/test_checks/test_history_warehouse.py` | Parity tests against the DuckDB connector. |
| `tests/test_dbt_package/` | Python-side invocation tests. |
| `docs/install/dbt.md` (already listed in #50) | Advocate links here from the package README. |
| `.github/workflows/dbt-hub.yml` | On release tag, create a GitHub Release that dbt Hub watches. |

**Files to MODIFY:**

| Path | Change |
|---|---|
| `litmus/checks/history.py` | Extract a `HistoryStoreProtocol` (typing.Protocol) from the existing SQLite class. Rename current class to `SqliteHistoryStore`. Keep a `HistoryStore` alias for backcompat. |
| `litmus/checks/runner.py` | Accept any `HistoryStoreProtocol`, not `HistoryStore` specifically. Type hint change only. |
| `litmus/cli.py` | Add `--backend {sqlite,warehouse,auto}` flag to `check`. Auto-detect per Decision 2. Threading through `runner.run_checks`. |
| `litmus/config/settings.py` | Load `backend:` key from `litmus.yml`. |
| `pyproject.toml` | No new deps (dbt is a runtime-only co-installed package, not a Python import). Keep `[dev]` extras unchanged. |
| `Makefile` | Add `make dbt-test` target that runs integration tests against DuckDB. |
| `docs/ARCHITECTURE.md` | Add "dbt package topology" mini-section under "v0.3 additions". |
| `README.md` | Add a "Run inside dbt" section right after the GitHub Action section. |

**Files to DELETE / DEPRECATE:**

- Nothing. The SQLite store stays the default for solo engineers.

**Cross-package dependencies:**

- **Blocks #54 (AI Q&A)** — `/ask` uses `WarehouseHistoryStore` to read
  the latest value when a metric has no recent `Run` row in the catalog DB
  (e.g. a fresh dbt-only install that never POSTed to `/api/v1/runs`).
- **Blocks #56 (release prep)** — dbt Hub submission is part of release.
- Does not block #50 (docs) or #53 (UI); those stub the "install in dbt"
  link and backfill content once #51 lands.

---

### 3.3 Task #52 — Slack sign-off (owner: `litmus-inspector`)

**Files to CREATE:**

| Path | Purpose |
|---|---|
| `litmus_api/slack/__init__.py` | Package marker. |
| `litmus_api/slack/signature.py` | Slack signing-secret HMAC verification. Mirror pattern from `litmus_api/routes/webhooks.py`. |
| `litmus_api/slack/blocks.py` | Block Kit message builders: sign-off prompt, approval confirmation, ask-result card. |
| `litmus_api/slack/client.py` | Thin outbound POST-to-webhook client (stdlib `urllib.request`, no `slack_sdk` dep). |
| `litmus_api/routes/slack.py` | FastAPI router under `/api/v1/slack`. Events, commands, interactions, signoff endpoints. |
| `litmus_api/migrations/versions/0006_signoff.py` | Alembic migration adding the 7 `signoff_*` columns to `metric_revisions`. |
| `docs/install/slack.md` (already listed in #50; Inspector contributes the how-it-works section) | Step-by-step setup. |
| `tests/test_slack/` | Route tests with signed request fixtures. |

**Files to MODIFY:**

| Path | Change |
|---|---|
| `litmus_api/models/__init__.py` | Add 7 columns to `MetricRevision`. Do not touch existing columns. |
| `litmus_api/routes/metrics.py` | After `_record_revision` inserts a row, fire `slack.notify_signoff_requested(revision)` if `LITMUS_SLACK_WEBHOOK_URL` set and (spec has `signoff_required: true` OR env flag `LITMUS_SLACK_SIGNOFF_ALL=true`). Wrapped in try/except — Slack failure must not break the upsert. |
| `litmus_api/main.py` | `app.include_router(slack.router, prefix="/api/v1")`. |
| `litmus_api/config.py` | Read the three `LITMUS_SLACK_*` env vars into settings. |
| `litmus/spec/metric_spec.py` | Add `signoff_required: bool = False` to `MetricSpec` (additive, defaults to False — no breaking change). Threaded through YAML parser; DSL ignores. |
| `litmus/parser/yaml_parser.py` | Read `signoff_required` from YAML header. |
| `litmus_api/serializers.py` | Include `signoff_required` in `spec_to_dict` output. |
| `schemas/v1/check-suite.schema.json` | **Not modified.** The signoff field is on the spec, not the run output. |
| `docs/ARCHITECTURE.md` | Add "Slack surface" subsection. |

**Files to DELETE / DEPRECATE:** None.

**Cross-package dependencies:**

- Depends on #50 for `docs/install/slack.md` skeleton (minor).
- **Blocks #54 (AI Q&A)** — `/api/v1/slack/commands` is the entry point for
  the `/ask` slash command. Inspector ships the route skeleton; Q&A owner
  fills in the command handler for `/ask`.
- Blocks #53 (UI) insofar as the metric detail page shows a "signoff: pending"
  chip — UI can use fixtures until Slack ships.

---

### 3.4 Task #53 — UI redesign (owner: `litmus-ui` — new specialist)

**Files to CREATE:**

| Path | Purpose |
|---|---|
| `ui/app/(marketing)/layout.tsx` | Route group with marketing nav (no org switcher). |
| `ui/app/(marketing)/page.tsx` | The new three-audience landing. |
| `ui/app/install/layout.tsx` | Install hub nav. |
| `ui/app/install/page.tsx` | Tab chooser (dbt / cli / hosted). |
| `ui/app/install/dbt/page.tsx` | dbt walkthrough. |
| `ui/app/install/cli/page.tsx` | CLI walkthrough. |
| `ui/app/install/hosted/page.tsx` | Docker-compose walkthrough. |
| `ui/app/install/slack/page.tsx` | Slack webhook setup (webhook URL + slash command config). |
| `ui/app/ask/page.tsx` | Standalone AI Q&A page. |
| `ui/app/badge/page.tsx` | Badge gallery + copy-paste snippets. |
| `ui/components/AskPanel.tsx` | Shared chat panel (sidebar + standalone). Consumes `/api/v1/ask`. |
| `ui/components/HeroBadgeDemo.tsx` | Auto-polling public demo badge. |
| `ui/components/Section.tsx` | Reusable landing section wrapper. |
| `ui/components/InstallTabs.tsx` | Segmented-control for the install page. |
| `ui/components/CopyButton.tsx` | Shared copy-to-clipboard for code blocks. |
| `ui/components/SignoffChip.tsx` | Small status chip for `metric_revisions.signoff_status`. |
| `ui/components/Nav.tsx` | New top-nav (replaces whatever is inlined in `layout.tsx`). |
| `ui/lib/ask.ts` | Client-side helper for `/api/v1/ask`. |

**Files to MODIFY:**

| Path | Change |
|---|---|
| `ui/app/layout.tsx` | Inject the new `<Nav>`. Keep `<body>` styling. Ensure marketing routes skip the authenticated chrome. |
| `ui/app/page.tsx` | Redirect to `/(marketing)` or serve the landing directly — one route, one decision. |
| `ui/app/metrics/page.tsx` | No structural change. Empty state rewritten to "Install in dbt" / "Install CLI" CTAs. |
| `ui/app/metrics/[slug]/page.tsx` | Add right-side `<AskPanel>` (collapsible), signoff chip next to the revision entries, and a small "Embed this badge" button near the `<TrustBadge>`. |
| `ui/components/TrustBadge.tsx` | Add `<title>Powered by Litmus</title>` SVG tooltip that links to the configured endpoint root (viral loop requirement). |
| `ui/lib/api.ts` | Add `postAsk(question, context)` helper. |
| `ui/lib/fixtures.ts` | Add fixture responses for `/api/v1/ask` so the UI renders pre-Inspector/pre-#54. |
| `ui/package.json` | No new deps preferred. If a charting lib is needed for the landing, use what's already present (Recharts). |
| `ui/tailwind.config.ts` | Extend theme only if the new landing requires additional colors for the audience sections. |

**Files to DELETE / DEPRECATE:**

- Any existing inlined nav in `ui/app/layout.tsx` — migrated into `Nav.tsx`.
- `litmus share` command's HTML output is NOT deleted from the CLI (still
  used for one-off artifacts) but the UI's landing deprioritises it.

**Cross-package dependencies:**

- Depends on #50 (`docs/positioning.md` copy for the landing).
- Depends on #54 for the live `/ask` endpoint, but can ship with fixture
  responses and flip to live on the release branch merge.
- Blocks #55 (badge polish) for the badge-gallery page — #55 owner consumes
  the `ui/app/badge/page.tsx` scaffold.

---

### 3.5 Task #54 — AI Q&A bot (owner: `litmus-inspector` or dedicated)

**Files to CREATE:**

| Path | Purpose |
|---|---|
| `litmus_api/ai/ask.py` | Claude-gated intent resolver. Mirrors structure of `litmus_api/ai/explain.py`. |
| `litmus_api/routes/ask.py` | `POST /api/v1/ask` — the engineer-callable surface. |
| `litmus/generators/sql_generator.py` (extend) | New function `build_ask_query(spec, time_window, filters) -> str`. |
| `docs/ai-ask.md` (already listed in #50) | Privacy disclosure. |
| `tests/test_ai/test_ask.py` | Stubbed Anthropic client, tests the tool-use contract and the 422 `unresolved` path. |
| `tests/test_generators/test_ask_query.py` | SQL generation + time-window parity. |

**Files to MODIFY:**

| Path | Change |
|---|---|
| `litmus_api/main.py` | `app.include_router(ask.router, prefix="/api/v1")`. |
| `litmus_api/config.py` | No new env vars — reuses `LITMUS_ANTHROPIC_API_KEY`. |
| `litmus_api/routes/slack.py` | `/api/v1/slack/commands` handler for `/ask <question>`: internal-call `ask.resolve_and_answer(...)`, format Block Kit card via `slack/blocks.py`. |
| `litmus_api/serializers.py` | Helper `spec_to_catalog_entry(spec)` → the trimmed dict Claude receives. |
| `litmus/connectors/base.py` | Add `execute_readonly_query(sql: str) -> list[dict]` — default implementation calls `execute_query` but marked `@readonly`. Connector subclasses that support session-level RO (Postgres `SET TRANSACTION READ ONLY`, Snowflake secondary role, BigQuery job labels) override. |
| `docs/ai-explanations.md` | Add a pointer to `docs/ai-ask.md`. |
| `pyproject.toml` | No new deps. Reuses `[ai]` extras. |

**Files to DELETE / DEPRECATE:** None.

**Cross-package dependencies:**

- Depends on #51's `WarehouseHistoryStore` for the "stale-value fallback" when
  the warehouse query fails but we have a recent `litmus_runs` row.
- Depends on #52 for the Slack `/ask` entry point (optional — the HTTP endpoint
  works without Slack).
- Depends on #53 for the UI `<AskPanel>` consumer (optional — the endpoint is
  independently useful).
- **Does not block** other tasks. It is the riskiest piece; schedule it to
  ship late, behind a feature flag if needed.

---

### 3.6 Task #55 — Badge distribution polish (owner: TBD; lightweight)

**Files to CREATE:**

| Path | Purpose |
|---|---|
| `ui/app/badge/page.tsx` (listed in #53) | Gallery with copy-paste snippets. |
| `docs/badges.md` (listed in #50) | Canonical embedding guide. |
| `docs/badges/notion.md` | Notion-specific embed + screenshot. |
| `docs/badges/slack-unfurl.md` | Slack unfurl setup — link preview for `/embed/*.svg`. |
| `docs/badges/confluence.md` | Confluence macro walkthrough. |
| `docs/badges/readme.md` | README badge markdown cheatsheet, shields.io-style. |
| `litmus_api/embed_slack_unfurl.py` | Slack link-unfurl payload builder (parses the embed token from the URL, returns a block-kit attachment). Stubbed into `litmus_api/routes/slack.py`'s `/events` handler. |

**Files to MODIFY:**

| Path | Change |
|---|---|
| `litmus_api/embed_svg.py` | Add `<title>Powered by Litmus — click for details</title>` as the SVG's top-level `<title>`. Add a `<a xlink:href="...">` wrapper around the whole badge that links back to the metric detail URL (configurable via `LITMUS_PUBLIC_URL`). **Viral loop requirement.** |
| `litmus_api/routes/embeds.py` | Add a `size=sm|md|lg` query param (275×36 stays the md default; sm=200×26 for tight spots, lg=400×52 for decks). |
| `README.md` | Replace the generic shields.io badges with a live Litmus badge example (against a demo token that the repo hosts). |
| `CONTRIBUTING.md` | One-line note: the live badge on README updates on every push thanks to the webhook. |

**Cross-package dependencies:**

- Depends on #52 for Slack link-unfurl registration (the Slack app config
  needs to declare `links.read` permission scope; docs only, no code
  dependency).
- Depends on #53 for `/badge` page scaffold.

---

### 3.7 Task #56 — Final cohesion + release prep (owner: team lead / Architect)

**Files to CREATE:**

| Path | Purpose |
|---|---|
| `docs/v0.3-launch-checklist.md` | Internal launch checklist (not user-facing). |
| `.github/workflows/dbt-hub-release.yml` | (If not yet in #51) Auto-create a dbt-hub-compatible release. |

**Files to MODIFY:**

| Path | Change |
|---|---|
| `pyproject.toml` | Bump version to `0.3.0`. Ensure `[ai]` and `[bi]` extras are unchanged (they work already). |
| `litmus/__init__.py` | `__version__ = "0.3.0"`. |
| `CHANGELOG.md` | Full v0.3 section: YAML parser, dbt package, Slack sign-off, `/ask`, UI redesign, badge polish. |
| `action.yml` | `branding` refresh only if icon/color changes; `inputs`/`outputs` stay identical. Add a one-line description update. |
| `examples/metrics/` | Sanity-check every existing metric still parses under both DSL + YAML (via a parametrised test in `tests/test_parser/`). |
| `docs/RELEASING.md` | Add v0.3 steps: tag release → dbt-hub PR → Slack app manifest attached → PyPI build. |

**Files to DELETE / DEPRECATE:** None.

**Cross-package dependencies:** Everything else. Runs last.

---

### 3.8 Dependency DAG (compressed)

```
          #50 docs/positioning (no blockers)
             │
             ├─────▶ #53 UI landing (depends on copy)
             │
             ├─────▶ #51 dbt package (install/dbt.md)
             │           │
             │           ├─▶ #54 AI Q&A (WarehouseHistoryStore)
             │           │
             ├─────▶ #52 Slack sign-off
             │           │
             │           ├─▶ #54 AI Q&A (Slack /ask entry)
             │           │
             │           └─▶ #55 Badge polish (unfurl docs only)
             │
             └─────▶ #55 Badge polish (badges.md)

    #56 release prep  ◀──────  ALL OF THE ABOVE
```

Parallelisable fronts:
- **#50 + #51** start same day. #50 unblocks the others' docs; #51 is
  mostly self-contained.
- **#52 + #53** start after #50 ships its copy skeleton (~2 days).
- **#54** starts after #51 lands `WarehouseHistoryStore` and #52 lands the
  Slack command route.
- **#55** starts in parallel with #53 (shared `/badge` page) and consumes
  #52's unfurl hook.

---

## 4. OSS attraction plan

### 4.1 dbt Hub listing

- Submit `litmus-data/litmus` to [`hub.getdbt.com`](https://hub.getdbt.com)
  via a PR to `dbt-labs/hub.getdbt.com` adding a `data/litmus-data/litmus/`
  entry pointing at GitHub releases.
- Hub requires: `dbt_project.yml` with a valid `name`, `version`,
  `require-dbt-version` (pin `>=1.6.0`), and a populated `README.md`.
- Release cadence: every minor version of the Python package cuts a matching
  dbt package release (same version number). Patch releases ship dbt updates
  only if the package code changes.
- First user-visible command after install:
  ```
  dbt deps
  dbt run --select litmus
  ```
  That's the 5-minute wow moment — a `litmus_runs` table appears in their
  warehouse, no CLI required.

### 4.2 Coalesce 2026 talk angle

Title candidate: **"Three Teams, Three Numbers: Why Your Revenue Metric
Disagrees With Itself — and a Live Badge That Proves It."**

Pitch:
1. Open with the three-numbers problem (the existing README hook is already
   the speaker-note gold).
2. Install the dbt package live. First `dbt run` writes `litmus_runs` rows.
3. Open Slack — `/ask what was revenue last month?` — get the answer with
   the trust badge inline.
4. Show the badge rendering in Notion, in a Confluence page, in a README.
5. Push a `.metric` change. The PM gets a Slack sign-off prompt. They
   approve. The revision log updates. Badge stays green.

Submit: late summer 2026 (Coalesce CFP typically opens May–June). Slot target:
"Workflow & productivity" track, 25-minute talk.

### 4.3 LLM-as-audience (MCP endpoint)

Novel angle: position `.metric` files as **canonical context for AI data
agents** (Glean, Dust, Delphi, Cursor's data-agent mode, Claude Projects,
custom GPTs).

New surface: `GET /api/v1/mcp/metrics` returning the full catalog in the
Model Context Protocol resource format:

```json
{
  "resources": [
    {
      "uri": "litmus://metric/monthly_revenue",
      "name": "Monthly Revenue",
      "description": "Total revenue from completed orders in the current calendar month.",
      "mimeType": "application/vnd.litmus.metric+json",
      "annotations": {
        "owner": "finance-team",
        "trust_status": "passed",
        "last_run": "2026-04-17T04:00:00Z",
        "primary_table": "orders"
      }
    }
  ]
}
```

Plus `GET /api/v1/mcp/metrics/{slug}` returning the full spec + latest run
summary as an MCP-friendly blob. We will NOT ship an MCP server in v0.3 —
just the HTTP surface. The MCP server is a ~30-line Node wrapper we open-source
separately in v0.4.

Why this matters:
- Every AI data agent being built in 2026 is looking for "authoritative
  metric definitions" that aren't a dbt `manifest.json` (too raw) or a
  Looker LookML (proprietary). `.metric` is small, readable, and ships with
  trust metadata.
- A published MCP catalog is a developer-marketing loop: every agent-maker
  integrating Litmus is another audience we reach.

### 4.4 Viral loop — badge backlinks

Every rendered badge includes:

1. An SVG `<title>` of "Powered by Litmus — click for details" (accessibility
   + hover tooltip).
2. An `<a xlink:href="{LITMUS_PUBLIC_URL}/metrics/{slug}">` wrapper making the
   entire badge clickable (works in README/Confluence; Notion strips it but
   the alt text remains).
3. A tiny `⚗ litmus` glyph in the bottom-right corner of the lg size (400×52).
   Not on the sm/md sizes — don't be annoying.
4. The SVG's `<desc>` tag includes the canonical metric URL as a bare string
   so even stripped embeds carry a text breadcrumb.

No tracking pixel, no analytics beacon. The loop is purely the URL.

### 4.5 Five-minute wow moment

Exact command sequence a new user runs to see a badge somewhere visible:

```bash
# 1. Install.
pip install litmus-data

# 2. Scaffold + seed a demo DuckDB.
litmus init demo-metrics --warehouse duckdb --yes
cd demo-metrics

# 3. Spin up the hosted catalog + badge server locally.
docker run -p 8080:8080 -e LITMUS_PUBLIC_URL=http://localhost:8080 \
  ghcr.io/zinnoberhaus/litmus:0.3

# 4. Run checks + push.
litmus check metrics/ --push http://localhost:8080

# 5. Grab the badge URL for the example metric.
curl -s http://localhost:8080/api/v1/metrics/example_revenue | jq -r '.embed_token' \
  | xargs -I{} echo "Badge: http://localhost:8080/embed/{}/badge.svg"
```

Total clock time on a laptop with Docker warm: ~90 seconds. The resulting
URL renders a green badge. Paste it into Notion, GitHub README, or Slack
message → viral loop kicks in.

We ship this exact sequence as `scripts/quickstart.sh` (task #56).

---

## 5. Risks

### 5.1 What could go wrong

| Risk | Probability | Impact | Mitigation |
|---|---|---|---|
| **YAML becomes de-facto primary; DSL drifts into legacy.** | Medium | Medium — we lose the PM-readable hook. | Enforce parity in CI: a parametrised test iterates every example and asserts DSL ↔ YAML round-trip produces identical `MetricSpec`. Architect reviews any PR that touches only one side. |
| **dbt package's macros-calling-Python shortcut is rejected by dbt Hub review.** | Low | Medium | Elementary does the same thing. If Hub reviewers push back, we fall back to pure-SQL macros for the 6 stateless rules and keep Python-shelled execution for the 3 stateful ones behind a `litmus.python_mode: true` flag. Integration testable on DuckDB without Hub approval. |
| **Slack webhook-only UX feels second-class vs a full Slack App.** | Medium | Low | Ship a clear "Upgrade to Slack App in v0.4" banner inside the Slack config docs. The webhook flow is genuinely acceptable — Linear, Dagster, and Prefect all ship webhook-only Slack integrations without complaints. |
| **`/ask` hallucinates a metric slug and the SQL runs against the wrong table.** | Medium | High | Hard-validate the returned slug against the existing catalog *before* generating SQL. Unknown slug → 404. Low confidence → 422 with suggestions. Time window is an enum, not free text. Filters are validated against the spec's declared columns. |
| **`/ask` generates SQL that melts the warehouse** (big scan, no limit). | Low | High | The generated SQL is templated from the spec; it uses whatever `WHERE`/`GROUP BY` the spec already declares. We add a hard `LIMIT 1` on the outer aggregation and a connector-level query timeout (30s default, configurable via `LITMUS_ASK_TIMEOUT_SECONDS`). Read-only connection where the connector supports it. |
| **Badge backlinks get flagged as tracking.** | Low | Low | No tracking pixel; link is to a public metric detail page the user themselves hosts. If hosted by us in future Cloud: a clear "opt out of powered-by link" env var. |
| **`MetricSpec` accidentally grows a breaking field during YAML parser impl.** | Medium | High | Architect reviews every `MetricSpec` edit. New fields MUST have safe defaults and appear in both parsers. CI check: `assert spec_to_dict(MetricSpec()) == {...}` against a golden fixture. |
| **dbt community expects `not_null` / `unique` parity and we don't ship it.** | High | Medium | We explicitly don't re-implement dbt's tests. Docs section: "Already have `dbt test`? Keep it. Litmus picks up your results via `_dbt_test_results` (imported through the existing `import-dbt` path)." Frames non-duplication as a feature. |
| **Slack signature verification is wrong and an attacker fires approvals.** | Low | High | Copy the GitHub webhook pattern verbatim (already in `litmus_api/routes/webhooks.py`). Test with Slack's own `validate_request` fixture. Reject timestamps older than 5 minutes. |

### 5.2 Signals that should make us pause & validate

- **dbt Hub review takes >3 weeks.** Something in our package is wrong;
  pull back and re-architect.
- **First 50 `/ask` queries have <40% resolved-with-correct-metric rate.**
  Our intent-resolution prompt is weak; switch from forced-tool to a
  retrieval-first approach (embed metrics, rank, then confirm).
- **`WarehouseHistoryStore` differs meaningfully from `SqliteHistoryStore`
  in test results.** The abstraction is leaking. Fix before dbt Hub launch.
- **Notion/Slack/Confluence users report broken badges.** SVG compatibility
  is narrower than we expect; pre-launch test via real embeds in all four
  platforms.
- **PMs never click approve in Slack.** The whole PM surface is vanity;
  reconsider whether sign-off should live elsewhere (email? PR comment?).

---

## 6. Out-of-scope for v0.3 (explicitly deferred)

The following are **intentionally not in v0.3** and any PR that sneaks them
in will be rejected:

| Deferred | Why | When |
|---|---|---|
| **Multi-tenancy, orgs, SSO, billing, audit log UI.** | Cloud wedge. OSS stays single-tenant with a default org. | v0.5 (Cloud launch). |
| **Full Slack App + OAuth + Marketplace listing.** | Weeks of Slack-specific work. Webhook MVP covers the UX for self-hosters. | v0.4 (Slack App). |
| **MCP server** (as a running process). | HTTP surface is enough for v0.3; MCP server is a separate repo. | v0.4. |
| **Anomaly detection / statistical alerting.** | Monte Carlo territory. We ship threshold-based rules. | Never as first-party; integrate with existing tools. |
| **`.metric` DSL grammar changes.** | Architect veto. YAML gets parity with the existing DSL; nothing new on either side. | Indefinite. |
| **Breaking changes to `MetricSpec`.** | Downstream code (Inspector, Connector, reporters, `litmus_api`, UI) depends on the dataclass shape. New fields are additive with defaults. | Indefinite. |
| **New JSON schema version (`v2/`).** | The shipped `v1` is stable. Only additive optional fields. | Only when a breaking shape change is unavoidable. |
| **`action.yml` contract changes.** | External users pin `@v0`. Inputs/outputs are promised stable. | Indefinite. |
| **Branch deployments / PR preview envs.** | Dagster territory. Already solved via the existing GitHub Action running against PR branches. | Never. |
| **Column-level lineage UI.** | Out of scope per `docs/DAGSTER_MODEL.md`. | Never. |
| **Managed AI key.** | Per-install BYO-key. Cloud can bundle later. | v0.5. |
| **Write-back from Litmus to BI tools.** | Direction of causation is wrong; we observe, we don't define inside Looker. | Never. |
| **Non-Python SDKs.** | HTTP is the SDK. Everything is stdlib-urllib callable. | Indefinite. |
| **dbt-native YAML spec inside `schema.yml meta:`.** | Interesting but adds a third parser path. v0.3 supports `.metric` + standalone YAML only. | v0.4. |
| **Multi-dimensional reconciliation / group-by BI diffs.** | Schema already supports it; UI + job don't. | v0.5. |

---

## 7. Architect's sign-off checklist (for #56)

Before v0.3.0 tags:

- [ ] No new tokens in `litmus/parser/lexer.py` (`_LINE_PATTERNS` unchanged).
- [ ] No new fields on `MetricSpec` beyond `signoff_required: bool = False`.
- [ ] `parse_metric_file(".metric")` and `parse_metric_file(".yml")` produce
      byte-identical `MetricSpec` for every file in `examples/metrics/`.
- [ ] JSON schema v1 unchanged. Any new response fields on `/api/v1/*`
      endpoints are additive and marked optional in their Pydantic models.
- [ ] `action.yml` diff is whitespace + description only.
- [ ] `litmus --help` measured cold-start stays under 200ms on CI runner
      (lazy imports preserved).
- [ ] dbt package installs cleanly on DuckDB, Postgres, Snowflake, BigQuery
      — at minimum the first two in CI.
- [ ] Slack signature verification has a dedicated test with a malformed
      timestamp and a malformed signature.
- [ ] `/ask` never ships Claude the warehouse row data — assert in a test
      that the prompt contains only `name/description/trust_rules/recent_runs`.
- [ ] Every new page under `ui/app/install/*` is mobile-readable at 375px.
- [ ] `docs/positioning.md` is the one source of user-facing copy; the
      README and landing quote from it, not the other way around.

---

**End of blueprint.** Specialists: claim your task via `TaskUpdate`, read
your section above, and raise questions back to Architect before touching
code that crosses a boundary.
