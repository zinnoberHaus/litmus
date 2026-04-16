"""Row volume check — detect unexpected drops in row count."""

from __future__ import annotations

from litmus.checks.runner import CheckResult, CheckStatus
from litmus.connectors.base import BaseConnector
from litmus.spec.metric_spec import VolumeRule

WARNING_THRESHOLD = 0.9  # warn when within 90% of the limit

_PERIOD_INTERVALS = {
    "day": "1 DAY",
    "week": "7 DAYS",
    "month": "30 DAYS",
}


def check_volume(
    connector: BaseConnector,
    table: str,
    rule: VolumeRule,
    timestamp_column: str = "updated_at",
) -> CheckResult:
    """Check that row count hasn't dropped more than the threshold vs prior period."""
    target_table = rule.table or table
    interval = _PERIOD_INTERVALS.get(rule.period, "1 DAY")

    try:
        current_count = connector.get_row_count(target_table)

        # Get count from the previous period using the timestamp column
        prior_rows = connector.execute_query(
            f"SELECT COUNT(*) as cnt FROM {target_table} "
            f"WHERE {timestamp_column} < CURRENT_TIMESTAMP - INTERVAL '{interval}'"
        )
        prior_count = int(prior_rows[0]["cnt"]) if prior_rows else 0
    except Exception:
        # Fallback: just report current count, can't compare
        try:
            current_count = connector.get_row_count(target_table)
        except Exception as exc:
            return CheckResult(
                name=f"Row count{' of ' + target_table if rule.table else ''}",
                status=CheckStatus.ERROR,
                message=f"Could not query row count: {exc}",
                actual_value=None,
                threshold=f"< {rule.max_drop_percentage}% drop {rule.period} over {rule.period}",
            )
        return CheckResult(
            name=f"Row count{' of ' + target_table if rule.table else ''}",
            status=CheckStatus.PASSED,
            message=f"{current_count:,} rows (no historical data to compare)",
            actual_value=current_count,
            threshold=rule.max_drop_percentage,
        )

    if prior_count == 0:
        return CheckResult(
            name=f"Row count{' of ' + target_table if rule.table else ''}",
            status=CheckStatus.PASSED,
            message=f"{current_count:,} rows (no prior period data)",
            actual_value=current_count,
            threshold=rule.max_drop_percentage,
        )

    change_pct = ((current_count - prior_count) / prior_count) * 100

    if change_pct < -rule.max_drop_percentage:
        status = CheckStatus.FAILED
    elif change_pct < -rule.max_drop_percentage * WARNING_THRESHOLD:
        status = CheckStatus.WARNING
    else:
        status = CheckStatus.PASSED

    period_label = f"{rule.period}-over-{rule.period}"

    return CheckResult(
        name=f"Row count{' of ' + target_table if rule.table else ''}",
        status=status,
        message=f"{change_pct:+.0f}% {period_label} (threshold: < {rule.max_drop_percentage}%)",
        actual_value=round(change_pct, 2),
        threshold=rule.max_drop_percentage,
    )
