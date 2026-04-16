"""JSON output reporter.

The shape emitted here is a **frozen public API** defined by
`schemas/v1/check-suite.schema.json`. CI integrations (Slack bots, dashboards,
PagerDuty webhooks) depend on it. Breaking changes require bumping
``SCHEMA_VERSION`` and keeping the v1 emitter for at least two minor versions.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone

from litmus.checks.runner import CheckSuite
from litmus.spec.metric_spec import MetricSpec

SCHEMA_VERSION = "v1"


def generate_json_report(
    specs_and_suites: list[tuple[MetricSpec, CheckSuite]],
    schema_version: str = SCHEMA_VERSION,
) -> str:
    """Generate a JSON report string conforming to the declared schema version."""
    if schema_version != SCHEMA_VERSION:
        raise ValueError(
            f"Unsupported schema_version: {schema_version!r}. "
            f"This Litmus build only emits {SCHEMA_VERSION!r}."
        )

    metrics = []
    for spec, suite in specs_and_suites:
        score, total = suite.trust_score
        checks = []
        for r in suite.results:
            checks.append({
                "name": r.name,
                "status": r.status.value,
                "message": r.message,
                "actual_value": r.actual_value,
                "threshold": r.threshold,
            })
        metrics.append({
            "name": spec.name,
            "description": spec.description,
            "owner": spec.owner,
            "tags": spec.tags,
            "sources": spec.sources,
            "trust_score": score,
            "trust_total": total,
            "checks": checks,
        })

    report = {
        "litmus_version": "0.1.0",
        "schema_version": SCHEMA_VERSION,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "metrics": metrics,
        "summary": {
            "total": len(metrics),
            "healthy": sum(
                1 for _, s in specs_and_suites
                if s.failed == 0 and s.errors == 0
                and s.warnings == 0
            ),
            "warning": sum(
                1 for _, s in specs_and_suites
                if s.warnings > 0 and s.failed == 0
            ),
            "failing": sum(
                1 for _, s in specs_and_suites
                if s.failed > 0 or s.errors > 0
            ),
        },
    }
    return json.dumps(report, indent=2, default=str)
