"""Generate SQL queries from a MetricSpec."""

from __future__ import annotations

from litmus.spec.metric_spec import MetricSpec


def generate_check_queries(spec: MetricSpec) -> dict[str, str]:
    """Generate SQL queries for each trust check in the spec.

    Returns a dict of check_name → SQL string.
    """
    queries: dict[str, str] = {}
    primary = spec.sources[0] if spec.sources else "UNKNOWN_TABLE"

    if spec.trust is None:
        return queries

    if spec.trust.freshness:
        queries["freshness"] = (
            f"SELECT MAX(updated_at) as last_updated\n"
            f"FROM {primary};"
        )

    for null_rule in spec.trust.null_rules:
        queries[f"null_rate_{null_rule.column}"] = (
            f"SELECT\n"
            f"  COUNT(*) as total_rows,\n"
            f"  COUNT(CASE WHEN {null_rule.column} IS NULL THEN 1 END) as null_count,\n"
            f"  ROUND(COUNT(CASE WHEN {null_rule.column} IS NULL THEN 1 END)"
            f" * 100.0 / COUNT(*), 2) as null_pct\n"
            f"FROM {primary};"
        )

    for volume_rule in spec.trust.volume_rules:
        table = volume_rule.table or primary
        queries[f"volume_{table}"] = (
            f"SELECT COUNT(*) as current_count\n"
            f"FROM {table};"
        )

    for _range_rule in spec.trust.range_rules:
        queries["value_range"] = (
            f"SELECT SUM(amount) as metric_value\n"
            f"FROM {primary};"
        )

    return queries
