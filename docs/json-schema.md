# Litmus JSON Report Schema

`litmus check --format json` emits a structured document that downstream
tools — Slack bots, dashboards, alerting pipelines — can parse reliably.
That document is a **public API**.

## Current version: `v1`

The canonical JSON Schema (draft 2020-12) is checked into the repo at:

    schemas/v1/check-suite.schema.json

Anything that reads Litmus JSON output should validate against that file.

## Top-level shape

```json
{
  "litmus_version": "0.1.0",
  "schema_version": "v1",
  "generated_at": "2026-04-16T21:00:00+00:00",
  "metrics": [ ... ],
  "summary": { "total": 3, "healthy": 2, "warning": 0, "failing": 1 }
}
```

| Field | Type | Notes |
|-------|------|-------|
| `litmus_version` | string | The Litmus package version that produced the report. |
| `schema_version` | string | Always `"v1"` for this schema. Pin this in consumers. |
| `generated_at` | ISO-8601 UTC | Report timestamp. |
| `metrics` | array | One entry per `.metric` file checked. |
| `summary` | object | Aggregate counts across all metrics. |

## Metric entry

```json
{
  "name": "Monthly Revenue",
  "description": "Total revenue from completed orders ...",
  "owner": "finance-analytics",
  "tags": ["finance", "revenue"],
  "sources": ["orders", "refunds"],
  "trust_score": 6.5,
  "trust_total": 7,
  "checks": [ ... ]
}
```

`trust_score` is a float: each passed check = 1.0, each warning = 0.5, failed/error = 0.0.
`trust_total` is the integer number of rules in the Trust block.

## Check entry

```json
{
  "name": "Null rate on amount",
  "status": "failed",
  "message": "Null rate on amount: 12.5% (threshold: < 5.0%) — FAILED",
  "actual_value": 12.5,
  "threshold": 5.0
}
```

`status` is one of `passed | warning | failed | error`.
`actual_value` and `threshold` types vary by rule — consumers should accept
`number | string | integer | boolean | null`.

## Compatibility policy

- **Additive changes** (new optional fields) are allowed within a major version. The JSON Schema marks objects as `additionalProperties: true` to make this explicit.
- **Breaking changes** (renamed fields, removed fields, reshaped types, changed enums) require a new major version (`v2`, `v3`, ...).
- When a new version ships, the previous version is kept for **at least two minor releases** so downstream consumers have time to migrate.

## Validating your output

```python
import json
from jsonschema import validate

report = json.loads(open("report.json").read())
schema = json.loads(open("schemas/v1/check-suite.schema.json").read())
validate(instance=report, schema=schema)
```

## Future versions

Planned for `v2`: history timestamps per check, explicit `rule_kind`
discriminator (so consumers can switch on the rule type without parsing
`name`), and structured `threshold` objects (min/max/period) instead of
flat scalars.
