# BI reconciliation

Reconciliation is the trust story for dashboards: the same metric computed in the warehouse AND in a BI tool (Looker / Tableau), flagged when the values disagree. Every reconciliation run writes one row per source into the catalog, so operators can see at a glance whether their $4.2M warehouse number matches the $3.8M on the CEO's Looker dashboard.

> **Status: scaffold.** The Looker and Tableau connectors are tested against mocked SDKs only. We have not yet verified the code against a live Looker or Tableau instance — running it end-to-end against your own BI tool is a welcome contribution.

## Install

The BI connectors are gated behind an optional extras group so `pip install litmus-data[server]` stays slim:

```bash
pip install 'litmus-data[bi]'
# or if you want everything
pip install 'litmus-data[all]'
```

This pulls in `looker-sdk>=23.0` and `tableauserverclient>=0.25`.

## Configure credentials

Credentials are env-var only — same convention as the warehouse connectors.

### Looker

| Env var | Example |
|---------|---------|
| `LITMUS_LOOKER_BASE_URL` | `https://mycorp.looker.com` |
| `LITMUS_LOOKER_CLIENT_ID` | from Admin → Users → *your user* → Edit Keys |
| `LITMUS_LOOKER_CLIENT_SECRET` | ditto |

### Tableau

| Env var | Example |
|---------|---------|
| `LITMUS_TABLEAU_SERVER_URL` | `https://10ax.online.tableau.com` |
| `LITMUS_TABLEAU_SITE_ID` | your site content URL, or `""` for the default site |
| `LITMUS_TABLEAU_PAT_NAME` | from Account Settings → Personal Access Tokens |
| `LITMUS_TABLEAU_PAT_VALUE` | the secret value shown when you create the PAT |

## Attach a BI mapping to a metric

Once your metric is in the catalog (via `litmus check --push` or a GitHub webhook), attach the Looker or Tableau equivalent with a `POST` to `/api/v1/metrics/{id}/bi-mappings`:

```bash
curl -X POST https://<your-litmus-server>/api/v1/metrics/monthly_revenue/bi-mappings \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer $LITMUS_API_KEY" \
  -d '{
    "source": "looker",
    "identifier": "ecommerce::orders.total_revenue"
  }'
```

Identifier format:

| Source | Format | Example |
|--------|--------|---------|
| `looker` | `<lookml_model>::<view>.<measure>` | `ecommerce::orders.total_revenue` |
| `tableau` | `<workbook_id>/<view_id>/<field_name>` | `wb-abc/view-xyz/SUM(Sales)` |

One mapping per `(metric, source)` — attempting to add a second Looker mapping for the same metric returns `409 Conflict`. Delete the existing mapping first if you need to change the identifier.

`GET /api/v1/metrics/{id}/bi-mappings` lists the attached mappings; `DELETE /api/v1/metrics/{id}/bi-mappings/{mapping_id}` removes one.

## Trigger a reconciliation

Reconciliation runs on demand — the server does not include a scheduler. Wire your own cadence (Airflow DAG, cron, Dagster sensor, …) that hits the trigger endpoint.

### From the CLI

```bash
litmus reconcile monthly_revenue \
  --endpoint https://<your-litmus-server> \
  --api-key "$LITMUS_API_KEY"
```

Renders a Rich table with one row per BI source, showing the BI value, the delta vs the latest warehouse run, and a pass/warn/fail bucket.

### Over HTTP

```bash
curl -X POST https://<your-litmus-server>/api/v1/metrics/monthly_revenue/reconcile \
  -H "Authorization: Bearer $LITMUS_API_KEY"
```

Returns the newly-written rows. Use `GET /api/v1/metrics/{id}/reconciliation` to read the latest state for the UI — that endpoint always includes a synthetic `"warehouse"` row at the top, even for metrics with no mappings and no runs yet.

## Thresholds

`|delta|` is the absolute proportional drift between warehouse and BI values.

| Delta | Status |
|-------|--------|
| `< 2%` | `pass` |
| `< 10%` | `warn` |
| `>= 10%` | `fail` |

If `warehouse_value` is zero or null, delta is forced to `0` and the row is marked `pass` — there's nothing to reconcile against.

## Error handling

A failing connector (bad creds, API outage, malformed identifier) does not break the rest of the job. The failing source gets a row with `status="fail"` and the exception message in the `error` column. The other mappings still run. This lets the UI render "Looker: errored with `<reason>`" next to a healthy Tableau row rather than silently dropping either.

## Scheduling (not included)

We deliberately do not ship a scheduler. Pick whichever you already run:

- Airflow: `PythonOperator` hitting the trigger endpoint.
- Dagster: a sensor or schedule that POSTs via `urllib.request`.
- cron: `curl -X POST ...` on whatever cadence your BI dashboards refresh.

## Related

- `CLAUDE.md` → "BI reconciliation" for the internal contract.
- `litmus_api/bi/base.py` — the `BaseBIConnector` ABC if you want to add a new BI tool.
