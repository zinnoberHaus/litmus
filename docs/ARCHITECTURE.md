# Litmus 0.2 — Architecture

**Status:** Draft. Target cut: 12-week MVP.
**Audience:** Backend engineers starting implementation. Frontend engineers consuming the API. Anyone evaluating the OSS/Cloud split.

0.1 shipped a CLI that parses `.metric` files, runs trust checks against a warehouse, and prints a report. 0.2 turns that output into a **system of record** — every metric gets a permanent URL, a history, an embeddable trust badge, and a lineage graph. The CLI stays. A web app + API join it. The hosted version multi-tenants the same binary.

This doc is the minimum spec a backend engineer needs to start on Tuesday.

---

## 1. System overview

```
                                 ┌──────────────────────────────────────────┐
                                 │             CUSTOMER REPO                │
                                 │                                          │
                                 │   metrics/*.metric   .github/workflows/  │
                                 │         │                    │           │
                                 │         │            ┌───────┴───────┐   │
                                 │         │            │ litmus check  │   │
                                 │         │            │  (GH Action)  │   │
                                 │         │            └───────┬───────┘   │
                                 │         │                    │           │
                                 │   ┌─────┴────────┐           │           │
                                 │   │  GitHub App  │           │           │
                                 │   │   webhook    │           │           │
                                 │   └─────┬────────┘           │           │
                                 └─────────┼────────────────────┼───────────┘
                                           │ push event         │ POST /runs
                                           ▼                    ▼
 ┌─────────────────────────────────────────────────────────────────────────────┐
 │                          LITMUS CONTROL PLANE                               │
 │                                                                             │
 │   ┌──────────────┐   ┌──────────────┐   ┌──────────────┐  ┌──────────────┐  │
 │   │  Next.js UI  │◀─▶│   FastAPI    │◀─▶│   Postgres   │  │    Redis     │  │
 │   │ (metric page)│   │   (REST)     │   │ (catalog +   │  │ (queue, rate │  │
 │   │              │   │              │   │  history)    │  │  limit, SVG  │  │
 │   └──────────────┘   └──────┬───────┘   └──────────────┘  │  cache)      │  │
 │                             │                             └──────────────┘  │
 │                             │                                               │
 │                  ┌──────────┼──────────┐                                    │
 │                  ▼          ▼          ▼                                    │
 │          ┌────────────┐ ┌────────┐ ┌──────────────┐                         │
 │          │ Ingestion  │ │  AI    │ │ Reconciler   │                         │
 │          │  workers   │ │ worker │ │   worker     │                         │
 │          │ (dbt, .met)│ │(Claude)│ │(warehouse vs │                         │
 │          └────────────┘ └────────┘ │    Looker)   │                         │
 │                                    └──────┬───────┘                         │
 └───────────────────────────────────────────┼─────────────────────────────────┘
                                             │ read-only queries
              ┌──────────────────────────────┼──────────────────────────────┐
              ▼                              ▼                              ▼
     ┌────────────────┐              ┌────────────────┐            ┌────────────────┐
     │   Warehouse    │              │     Looker     │            │   Tableau /    │
     │ (DuckDB/SF/BQ/ │              │   (LookML +    │            │     Mode       │
     │   Postgres)    │              │  Content API)  │            │                │
     └────────────────┘              └────────────────┘            └────────────────┘
```

**OSS core (Apache 2.0):**
- The existing CLI (`litmus check|parse|explain|report|share`).
- The Python library: `parser/`, `spec/`, `checks/`, `connectors/`, `reporters/`, `generators/`.
- The 0.2 API server (FastAPI) — single-tenant, anyone can run it.
- The 0.2 Next.js frontend — single-tenant.
- `docker-compose.yml` that brings up Postgres + Redis + API + UI against a local warehouse.
- SQLite history store stays for CLI-only users who never stand up Postgres.

**Cloud-only (closed source, MIT-NC or source-available):**
- Multi-tenant control plane (orgs, billing, SSO, audit log).
- Managed GitHub App.
- BI connectors that require OAuth app registration (Looker, Tableau, Mode).
- Embed service with usage metering (the `$20/1k views` SKU).
- AI "why did this fail" worker (uses our Anthropic key; self-hosters bring their own).
- Cross-source reconciliation scheduler.
- Hosted PostgreSQL + Redis + blob storage.

The boundary is **tenancy + managed credentials + metering**, not features. Self-hosters get the same metric detail page; they just run it on one org with one warehouse.

---

## 2. Data model

Postgres 15+. UUIDv7 primary keys so we get time-ordering for free. All tables soft-deletable via `deleted_at`. Timestamps in UTC.

```sql
-- ─────────────────────────────────────────────────────────────────────────────
-- Tenancy
-- ─────────────────────────────────────────────────────────────────────────────

CREATE TABLE orgs (
    id              UUID PRIMARY KEY,
    slug            TEXT NOT NULL UNIQUE,            -- URL segment, e.g. "acme"
    name            TEXT NOT NULL,
    plan            TEXT NOT NULL DEFAULT 'oss',     -- oss | team | business
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    deleted_at      TIMESTAMPTZ
);

CREATE TABLE users (
    id              UUID PRIMARY KEY,
    email           CITEXT NOT NULL UNIQUE,
    name            TEXT,
    password_hash   TEXT,                            -- null if SSO-only
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    deleted_at      TIMESTAMPTZ
);

CREATE TABLE org_members (
    org_id          UUID NOT NULL REFERENCES orgs(id) ON DELETE CASCADE,
    user_id         UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    role            TEXT NOT NULL,                   -- owner | admin | member | viewer
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (org_id, user_id)
);

CREATE TABLE api_keys (
    id              UUID PRIMARY KEY,
    org_id          UUID NOT NULL REFERENCES orgs(id) ON DELETE CASCADE,
    prefix          TEXT NOT NULL,                   -- "lmk_live_8chars", shown in UI
    hash            TEXT NOT NULL,                   -- argon2(secret)
    scopes          TEXT[] NOT NULL,                 -- ["ingest","read","embed:*"]
    created_by      UUID REFERENCES users(id),
    last_used_at    TIMESTAMPTZ,
    expires_at      TIMESTAMPTZ,
    revoked_at      TIMESTAMPTZ,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- Single-metric, no-login token for public embeds. Rotatable. Rate-limited separately.
CREATE TABLE embed_keys (
    id              UUID PRIMARY KEY,
    org_id          UUID NOT NULL REFERENCES orgs(id) ON DELETE CASCADE,
    metric_id       UUID NOT NULL,                   -- FK added after metrics table
    token           TEXT NOT NULL UNIQUE,            -- "lme_<40char>"
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    revoked_at      TIMESTAMPTZ
);

-- ─────────────────────────────────────────────────────────────────────────────
-- Metric catalog
-- ─────────────────────────────────────────────────────────────────────────────

CREATE TABLE metrics (
    id              UUID PRIMARY KEY,
    org_id          UUID NOT NULL REFERENCES orgs(id) ON DELETE CASCADE,
    slug            TEXT NOT NULL,                   -- "revenue_daily"
    name            TEXT NOT NULL,                   -- human title from Header
    description     TEXT,
    owner_email     TEXT,
    source_repo     TEXT,                            -- "acme/warehouse"
    source_path     TEXT,                            -- "metrics/revenue.metric"
    source_sha      TEXT,                            -- last ingested commit
    spec_json       JSONB NOT NULL,                  -- MetricSpec serialized
    spec_text       TEXT NOT NULL,                   -- raw .metric file
    primary_table   TEXT,                            -- spec.sources[0]
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    deleted_at      TIMESTAMPTZ,
    UNIQUE (org_id, slug)
);

ALTER TABLE embed_keys
    ADD CONSTRAINT embed_keys_metric_fk
    FOREIGN KEY (metric_id) REFERENCES metrics(id) ON DELETE CASCADE;

-- ─────────────────────────────────────────────────────────────────────────────
-- Runs and check results (history)
-- ─────────────────────────────────────────────────────────────────────────────

-- One row per `litmus check` invocation for one metric.
CREATE TABLE runs (
    id                   UUID PRIMARY KEY,
    org_id               UUID NOT NULL REFERENCES orgs(id) ON DELETE CASCADE,
    metric_id            UUID NOT NULL REFERENCES metrics(id) ON DELETE CASCADE,
    started_at           TIMESTAMPTZ NOT NULL,
    finished_at          TIMESTAMPTZ,
    status               TEXT NOT NULL,              -- passed | warning | failed | error
    trust_score          NUMERIC(5,4),               -- 0..1
    commit_sha           TEXT,
    ci_run_id            TEXT,
    triggered_by         TEXT NOT NULL,              -- github_app | cli | scheduled | api
    value_sum            NUMERIC,                    -- headline metric value this run
    row_count            BIGINT,
    schema_fingerprint   TEXT,
    column_means_json    JSONB,
    created_at           TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX runs_metric_time_idx ON runs (metric_id, started_at DESC);

-- One row per trust rule evaluated in a run.
CREATE TABLE check_results (
    id              UUID PRIMARY KEY,
    run_id          UUID NOT NULL REFERENCES runs(id) ON DELETE CASCADE,
    rule_type       TEXT NOT NULL,                   -- freshness|null|volume|range|change|...
    rule_json       JSONB NOT NULL,                  -- the rule config
    status          TEXT NOT NULL,                   -- passed|warning|failed|error
    message         TEXT,
    actual_value    NUMERIC,
    threshold_value NUMERIC,
    duration_ms     INTEGER
);

CREATE INDEX check_results_run_idx ON check_results (run_id);

-- ─────────────────────────────────────────────────────────────────────────────
-- Lineage
-- ─────────────────────────────────────────────────────────────────────────────

-- Nodes are URNs: "warehouse://snowflake/analytics/orders",
--                 "metric://<metric_id>", "bi://looker/dashboards/42",
--                 "doc://notion/<page_id>"
CREATE TABLE lineage_edges (
    id              UUID PRIMARY KEY,
    org_id          UUID NOT NULL REFERENCES orgs(id) ON DELETE CASCADE,
    upstream_urn    TEXT NOT NULL,
    downstream_urn  TEXT NOT NULL,
    edge_type       TEXT NOT NULL,                   -- derives_from | embedded_in | references
    source          TEXT NOT NULL,                   -- dbt | looker | tableau | manual
    discovered_at   TIMESTAMPTZ NOT NULL DEFAULT now(),
    last_seen_at    TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (org_id, upstream_urn, downstream_urn, edge_type)
);

CREATE INDEX lineage_upstream_idx   ON lineage_edges (org_id, upstream_urn);
CREATE INDEX lineage_downstream_idx ON lineage_edges (org_id, downstream_urn);

-- ─────────────────────────────────────────────────────────────────────────────
-- BI sources and reconciliation
-- ─────────────────────────────────────────────────────────────────────────────

CREATE TABLE bi_sources (
    id              UUID PRIMARY KEY,
    org_id          UUID NOT NULL REFERENCES orgs(id) ON DELETE CASCADE,
    kind            TEXT NOT NULL,                   -- looker|tableau|mode|metabase
    name            TEXT NOT NULL,
    base_url        TEXT NOT NULL,
    credentials_ref TEXT NOT NULL,                   -- pointer into secrets store
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    disabled_at     TIMESTAMPTZ
);

-- One row per (metric, bi_source, run) triple when we've pulled the same
-- number from both the warehouse and the BI tool.
CREATE TABLE reconciliations (
    id                   UUID PRIMARY KEY,
    org_id               UUID NOT NULL REFERENCES orgs(id) ON DELETE CASCADE,
    metric_id            UUID NOT NULL REFERENCES metrics(id) ON DELETE CASCADE,
    bi_source_id         UUID NOT NULL REFERENCES bi_sources(id) ON DELETE CASCADE,
    bi_object_urn        TEXT NOT NULL,              -- "bi://looker/looks/1234"
    warehouse_value      NUMERIC,
    bi_value             NUMERIC,
    delta_pct            NUMERIC,
    status               TEXT NOT NULL,              -- match | drift | mismatch | error
    checked_at           TIMESTAMPTZ NOT NULL DEFAULT now(),
    detail_json          JSONB
);

CREATE INDEX reconciliations_metric_idx ON reconciliations (metric_id, checked_at DESC);
```

Partitioning: `runs` and `check_results` by `started_at` month once a tenant crosses ~10M rows. Day-0 we don't need it.

---

## 3. API surface

FastAPI, JSON only, versioned under `/api/v1`. Same binary serves OSS and Cloud — Cloud injects a tenant middleware that scopes every query by `org_id` extracted from the API key or session cookie.

All write endpoints idempotent via `Idempotency-Key` header.

```
# ── Auth ─────────────────────────────────────────────────────────────────────
POST   /api/v1/auth/signup                 { email, password }
POST   /api/v1/auth/login                  { email, password } → { session_token }
POST   /api/v1/auth/logout
GET    /api/v1/auth/me                     → { user, orgs[] }
POST   /api/v1/auth/api_keys               { name, scopes[] } → { key (shown once) }
DELETE /api/v1/auth/api_keys/:id
POST   /api/v1/orgs                        { name, slug }
GET    /api/v1/orgs/:slug/members

# ── Metrics (catalog) ────────────────────────────────────────────────────────
GET    /api/v1/metrics                     ?q=&status=&owner=&page=
POST   /api/v1/metrics                     { spec_text, source_path, source_sha } → metric
GET    /api/v1/metrics/:id                 → full metric + latest run
PATCH  /api/v1/metrics/:id                 { description?, owner_email?, spec_text? }
DELETE /api/v1/metrics/:id

# ── Metric-scoped views ──────────────────────────────────────────────────────
GET    /api/v1/metrics/:id/history         ?from=&to=&limit=   → runs[]
GET    /api/v1/metrics/:id/runs/:run_id    → run + check_results[]
GET    /api/v1/metrics/:id/lineage         ?depth=2            → nodes[], edges[]
GET    /api/v1/metrics/:id/reconciliations ?limit=
POST   /api/v1/metrics/:id/explain         → AI-generated "why did this fail" (Cloud only)

# ── Ingestion ────────────────────────────────────────────────────────────────
POST   /api/v1/runs                        { metric_slug, status, trust_score,
                                             check_results[], commit_sha, ... }
POST   /api/v1/ingest/dbt                  multipart manifest.json → { metrics_created }
POST   /api/v1/ingest/github/webhook       (GitHub App payload, signature-verified)

# ── Embeds (public, token-auth, no session) ──────────────────────────────────
GET    /embed/:token/badge.svg             → cached SVG (10 min, stale-while-revalidate)
GET    /embed/:token/card.html             → iframe-safe card
GET    /embed/:token.json                  → tiny JSON for custom renderers

# ── BI sources ───────────────────────────────────────────────────────────────
POST   /api/v1/bi_sources                  { kind, name, base_url, credentials }
GET    /api/v1/bi_sources
POST   /api/v1/bi_sources/:id/sync         → kick off lineage scrape
DELETE /api/v1/bi_sources/:id
```

The JSON shape of `runs` / `check_results` is the existing `schemas/v1/check-suite.schema.json` extended with IDs. Do not break v1 — add `v2` if the shape changes (same rule the CLI already follows).

---

## 4. Ingestion flows

Three supported paths. They converge on `POST /api/v1/runs`.

**Path A — GitHub App (Cloud, recommended)**

```
 dev pushes .metric             ┌───── install GitHub App once ─────┐
         │                      │                                   │
         ▼                      ▼                                   │
   ┌──────────┐          ┌─────────────┐                            │
   │ GitHub   │── push ─▶│ webhook     │                            │
   │ repo     │          │ /ingest/gh  │                            │
   └──────────┘          └──────┬──────┘                            │
                                │                                   │
                                ▼                                   │
                         enqueue "ingest_repo" ─▶ worker            │
                                │                                   │
                                ▼                                   │
              worker: clone repo at sha,                            │
                      parse every *.metric,                        │
                      upsert into `metrics`,                       │
                      emit lineage edges from `source`,            │
                      ack webhook                                  │
                                                                    │
   (no check results yet — this ingests the *catalog*, not runs)    │
```

**Path B — CLI / GitHub Action (OSS-compatible)**

The existing `litmus check` gains a `--push <url> --api-key $LITMUS_API_KEY` pair of flags. After each local run it POSTs to `/api/v1/runs`. This is the path self-hosters use; it's also what we ship in the GitHub Action so customer warehouse credentials never leave their infra.

```
 GitHub Action step:
   - uses: litmus-data/litmus-action@v1
     with:
       path: metrics/
       endpoint: https://cloud.litmus.dev
       api-key: ${{ secrets.LITMUS_API_KEY }}
```

Action steps: parse → run checks against customer warehouse → POST results. Credentials for the warehouse stay in the customer's CI secrets. Credentials for Litmus are a single API key.

**Path C — Scheduled pull (Cloud only, opt-in)**

For customers who don't want CI: we register a deploy key, clone their repo on a cron, parse `.metric` files for catalog updates, and ask them to POST runs separately. We **never** run trust SQL from our infra by default — see section 5.

dbt ingestion (`POST /api/v1/ingest/dbt`) is a special case of Path A — either the GitHub App finds `target/manifest.json` in the repo, or the user uploads it manually. We call the existing `generators/dbt_importer.py` server-side to emit `MetricSpec` records.

---

## 5. Trust check execution

**Default: checks run on customer infra. We store only results.**

This is a security posture, not a technical limitation. Analytics teams will not paste Snowflake credentials into a third-party web form. The 0.1 CLI already runs in the customer's shell or CI runner with their creds; 0.2 keeps that model and bolts "POST results to Litmus" onto the end.

```
 ┌─────────── customer CI ───────────┐     ┌──────── Litmus Cloud ────────┐
 │                                   │     │                              │
 │  litmus check metrics/            │     │                              │
 │   │                               │     │                              │
 │   ├─▶ read warehouse creds        │     │                              │
 │   │   from CI secrets             │     │                              │
 │   │                               │     │                              │
 │   ├─▶ connect warehouse, run SQL  │     │                              │
 │   │                               │     │                              │
 │   └─▶ POST /api/v1/runs ──────────┼─────┼▶ insert runs + check_results │
 │       Authorization: Bearer lmk_* │     │  update metrics.updated_at   │
 │                                   │     │  bust embed SVG cache        │
 └───────────────────────────────────┘     └──────────────────────────────┘
```

**Opt-in: Cloud-executed checks** (deferred past MVP, but design for it).

Customer creates a **read-only** warehouse role, stores creds in our secrets store (AWS KMS-encrypted, per-org DEK), and we run checks from a locked-down VPC on a schedule. Gated behind an explicit toggle per `bi_source`/warehouse connection. Not in the 12-week cut; the schema (`credentials_ref` on `bi_sources`) already supports it.

Reconciliation (section 6) does run on our infra, but only against **BI tool APIs** (Looker/Tableau) that the customer has already OAuth'd. No raw warehouse creds ever.

---

## 6. Cross-source reconciliation

Goal: for a metric `revenue_daily`, on a schedule, ask "what does the warehouse say today? what does Looker Look #1234 say today? do they match?" and write a row to `reconciliations`.

```
                    ┌─── scheduler (every 1h) ───┐
                    │                            │
                    ▼                            │
        ┌─────────────────────┐                  │
        │  reconciler worker  │                  │
        └─────────┬───────────┘                  │
                  │                              │
        ┌─────────┴──────────┐                   │
        ▼                    ▼                   │
 ┌────────────┐       ┌────────────┐             │
 │ Warehouse  │       │   Looker   │             │
 │ value for  │       │ Content API│             │
 │ metric X   │       │ → Look 1234│             │
 └─────┬──────┘       └─────┬──────┘             │
       │                    │                    │
       └────────┬───────────┘                    │
                ▼                                │
         compare, compute                        │
         delta_pct, status                       │
                │                                │
                ▼                                │
       insert into reconciliations ──────────────┘
                │
                ▼
       if status != 'match':
           flip metric card badge to warning
           fire webhook / AI worker
```

**Where pieces live:**

- The Looker/Tableau/Mode **client libraries** (OAuth, pagination, rate limiting) live in `litmus/integrations/bi/` — OSS so self-hosters can wire them up with their own OAuth app registration.
- The **scheduler + worker loop** is Cloud-only. Self-hosters can invoke the same reconciler as a one-shot CLI command (`litmus reconcile <metric>`), but we don't ship a daemon in OSS.
- The **warehouse query** re-uses `litmus/connectors/` — specifically `get_column_sum`. The SQL is derived from the `MetricSpec` (we already have `generators/sql_generator.py`; extend it to emit a "single headline number" query).
- The **BI value extraction** is per-connector and lives next to the client. Looker: `run_look(look_id)` → pick a column. Tableau: data-server query.

MVP scope: only Looker, only "one scalar number per metric per BI object", only "match if within 0.5%". Multi-dimensional reconciliation (group-by revenue-by-region warehouse vs Looker) is post-MVP but the `detail_json` column on `reconciliations` is there to grow into it.

---

## 7. Deployment topology

**OSS — single-tenant, docker-compose.**

```yaml
# docker-compose.yml (sketch)
services:
  postgres:   { image: postgres:16, volumes: [pgdata:/var/lib/postgresql/data] }
  redis:      { image: redis:7 }
  api:        { build: ./litmus-api,  depends_on: [postgres, redis] }
  worker:     { build: ./litmus-api,  command: rq worker, depends_on: [redis] }
  ui:         { build: ./litmus-ui,   depends_on: [api] }
  # warehouse is BYO — user points the API at their own DuckDB/Postgres/Snowflake
```

One org row, one user row, everyone's an admin. No billing, no SSO, no metering. The embed SVG endpoint still works — use it locally to iframe a badge into a Notion page you self-host.

**Cloud — multi-tenant on AWS.**

```
           Route53
              │
              ▼
          CloudFront  ── /embed/*  ── S3 (SVG cache, 10-min TTL)
              │
              ▼
     ALB (api.litmus.dev, app.litmus.dev)
              │
      ┌───────┼────────┐
      ▼       ▼        ▼
   Next.js  FastAPI  Workers (ECS Fargate, 3 pools: ingest, reconciler, ai)
              │        │
              └────┬───┘
                   │
        ┌──────────┼──────────┐
        ▼          ▼          ▼
     RDS       ElastiCache  KMS (per-org DEK)
   (Postgres)   (Redis)
```

Control plane = a thin service that owns: orgs, billing (Stripe), SSO, audit log, embed usage metering. Everything else is the same binary as OSS, with `TENANT_MODE=cloud` flipped on and a `org_id` middleware pulling from JWT claims.

One DB cluster, row-level scoping via `org_id`. Separate DBs per tenant are a pricing/enterprise upsell, not the default — the ops cost of N databases dominates at low tenant count.

---

## 8. Auth model

Three principal types, three token shapes:

| Principal | Token | Auth header | Scope |
|---|---|---|---|
| Human in browser | Session cookie | cookie | full org access per role |
| Machine (CI, CLI) | API key `lmk_live_*` | `Authorization: Bearer` | scopes[]: `ingest`, `read`, `admin` |
| Public embed | Embed token `lme_*` | URL path component | single metric, read-only, rate-limited |

- **Roles** on `org_members`: `owner` (billing), `admin` (manage keys/members), `member` (push runs, create metrics), `viewer` (read-only UI).
- **API key scopes**: keep it coarse. `ingest` lets you POST runs and upsert metrics from CI. `read` lets you GET. `admin` lets you rotate other keys. GitHub App installations get a managed `ingest`-scoped key.
- **Embed keys** are the interesting primitive. One key per (metric, rotatable). Embedded in the URL path (`/embed/lme_xyz.../badge.svg`) so Notion/Slack/Confluence can render via plain `<img>`. Revoking a key breaks only that one embed. Rate-limited per-token per-IP to prevent abuse (Business plan meters these for billing).
- **SSO** (Google, Okta SAML): Cloud-only, surfaced via `/auth/sso/:provider`. OSS stays email+password.
- **Audit log**: one table, append-only, every write endpoint logs `(org_id, actor, action, resource_id, ts, ip, ua)`. Cloud only; OSS ships the code but no UI for it.

---

## 9. What stays OSS, what stays Cloud-only

The rule: **the core loop is OSS, the managed scale-outs are Cloud.** A self-hoster must be able to ship metrics to their team today without ever seeing our domain.

| Capability | OSS | Cloud | Notes |
|---|---|---|---|
| `.metric` DSL parser | ✅ | ✅ | Same code. |
| Trust checks (all rule types) | ✅ | ✅ | Same code. |
| Warehouse connectors | ✅ | ✅ | Same code. |
| CLI (`check|parse|explain|report|share`) | ✅ | ✅ | Unchanged. |
| FastAPI server (single-tenant) | ✅ | — | Cloud runs the multi-tenant build of it. |
| Next.js metric detail page | ✅ | ✅ | Same code; Cloud adds org switcher, billing pages. |
| Metric catalog / history (Postgres) | ✅ | ✅ | Self-host BYO Postgres; Cloud provides. |
| Embed SVG endpoint | ✅ | ✅ | Unmetered OSS; metered in Cloud (Business SKU). |
| GitHub App | — | ✅ | Needs a registered app + webhook secret we own. |
| BI connectors (Looker/Tableau) | ✅ (client libs) | ✅ (managed OAuth) | OSS users bring their own OAuth app; Cloud ships one. |
| Scheduled reconciler daemon | — | ✅ | OSS has one-shot `litmus reconcile` CLI. |
| AI "why did this fail" | ❌ (bring-your-own-key hook) | ✅ | OSS exposes `hooks.on_failure(run)` so users can wire Claude themselves. |
| SSO (Google/Okta) | — | ✅ | |
| Audit log UI | — | ✅ | Table exists in both; OSS just has no pages for it. |
| Billing, usage metering | — | ✅ | |
| Multi-tenant control plane | — | ✅ | |

**Not negotiable:** the metric detail page, the JSON/HTML reporters, and the embed SVG endpoint are OSS. They are the wedge. If a self-hoster can't put a live trust badge in Notion without paying us, the moat evaporates.

**Also not negotiable:** the Cloud GitHub App, scheduled reconciler, and AI explainer stay closed. They're the pieces that hurt to run ops for — that's exactly where hosted should pay.

---

## 10. Migration from 0.1.x

0.1.x users are a small population (the CLI has been out weeks). We err toward preserving their flow over backward-compat purity.

**Preserved (no change):**

- `.metric` file syntax. Zero DSL changes in 0.2. (Architect will veto any that sneak in.)
- `MetricSpec` dataclass shape. Downstream code contract holds.
- CLI subcommands `check|parse|explain|report|share|init`.
- JSON output of `litmus check -f json` — still v1 schema. 0.2 adds an *optional* `run_id` and `metric_id` field; everything else is unchanged.
- Exit code contract for `litmus check`. The GitHub Action (`action.yml`) inputs/outputs are unchanged.
- SQLite history store at `~/.litmus/history.db`. It keeps working for CLI-only users. The new Postgres history is opt-in via `--push <url>`.

**Breaking (explicit 0.2 migration notes):**

- `litmus share` HTML output is deprecated in favor of the hosted metric detail page. The command stays for one minor version and prints a deprecation notice suggesting `litmus check --push`. Remove in 0.3.
- The `trust_score` field of `CheckSuite` adds two decimal places of precision (it was `float` rounded, now `NUMERIC(5,4)` server-side). Reports render the same; any user doing byte-exact diffs of JSON will see a change.
- `action.yml` gains an optional `api-key` input. Without it, the action behaves exactly like 0.1. With it, results are pushed to a Litmus server.

**New surface (purely additive):**

- `litmus push <path>` — one-shot ingest a metric directory into a running Litmus server. Useful for one-off CLI-driven ingestion without CI.
- `litmus login` — OAuth device flow for Cloud, writes `~/.litmus/credentials`.
- `LITMUS_ENDPOINT` and `LITMUS_API_KEY` env vars. When both are set, every `litmus check` auto-pushes.

**Data migration:**

No existing 0.1 user has a Postgres catalog — there's nothing to migrate. First time a user runs `litmus push`, we bootstrap their org and upsert metrics from the current run. SQLite history is *not* backfilled automatically; we expose a one-time `litmus migrate history --to <endpoint>` script that replays local runs into the server.

---

## Open questions (post-MVP, flagged here so we don't forget)

1. **Multi-dimensional reconciliation.** The schema supports it (`detail_json`); the UI and scheduler don't. Needed before we can sell to anyone doing revenue-by-region.
2. **Spec versioning.** `metrics.spec_json` is a live pointer — history is only via `runs`. If a metric's definition changes, do we snapshot the old spec? Probably yes, via `metric_revisions` table. Defer.
3. **BI write-back.** Today reconciliation is read-only. A high-value future feature is "auto-update the Looker model from the `.metric` file." Not MVP; don't design for it yet but don't paint ourselves into a corner.
4. **Embed abuse.** The Business SKU is $20/1k card views. We need both metering (cheap, Redis counters) and abuse detection (someone iframes a badge on a 1M-view page). Rate limit per token + per IP; alert when a single token exceeds 10x its 30-day baseline.
5. **Python-free clients.** The CLI is the one Python dep. Everything else (API server aside) should be consumable from any language via HTTP. No Python SDK requirement on the customer side.

---

## Appendix — File layout after 0.2

```
litmus/                          # existing OSS Python package, unchanged
  parser/  spec/  checks/  connectors/  generators/  reporters/  cli.py

litmus_api/                      # new — FastAPI app
  main.py
  routes/   (auth.py metrics.py runs.py lineage.py embeds.py ingest.py)
  models/   (SQLAlchemy)
  workers/  (rq tasks: ingest_repo, reconcile, ai_explain)
  integrations/bi/  (looker.py tableau.py mode.py)
  migrations/       (alembic)

litmus_ui/                       # new — Next.js 14 app router
  app/
    (marketing)/
    [org]/metrics/[slug]/page.tsx         ← the metric detail page
    [org]/metrics/[slug]/history/
    [org]/metrics/[slug]/lineage/
    embed/[token]/badge.svg/route.ts      ← SVG generation

deploy/
  docker-compose.yml             # OSS
  helm/                          # Cloud (post-MVP)
  terraform/                     # Cloud (post-MVP)
```

---

**Reviewer checklist (Architect sign-off requires all ✅):**

- [ ] No `.metric` DSL changes implied by this doc.
- [ ] `MetricSpec` is still the only type crossing the parser boundary.
- [ ] Warehouse creds never enter the Cloud DB as plaintext (OR feature is explicitly scoped to post-MVP and behind a flag).
- [ ] JSON schema v1 is untouched; all new fields are additive and optional.
- [ ] Every OSS feature in section 9 is buildable without an Anthropic API key, a GitHub App, or a Stripe account.
