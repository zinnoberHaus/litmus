"""Data freshness check — how recently was the source table updated?"""

from __future__ import annotations

from datetime import datetime, timezone

from litmus.checks.runner import CheckResult, CheckStatus
from litmus.connectors.base import BaseConnector
from litmus.spec.metric_spec import FreshnessRule

WARNING_THRESHOLD = 0.9  # warn when within 90% of the limit


def check_freshness(
    connector: BaseConnector,
    table: str,
    rule: FreshnessRule,
    timestamp_column: str | None = None,
) -> CheckResult:
    """Check that the source table was updated within the freshness window."""
    try:
        last_updated = connector.get_table_freshness(table, timestamp_column)
    except Exception as exc:
        return CheckResult(
            name="Freshness",
            status=CheckStatus.ERROR,
            message=f"Could not query freshness: {exc}",
            actual_value=None,
            threshold=f"< {rule.max_hours} hours",
        )

    if last_updated is None:
        return CheckResult(
            name="Freshness",
            status=CheckStatus.ERROR,
            message="No timestamp data found in table.",
            actual_value=None,
            threshold=f"< {rule.max_hours} hours",
        )

    now = datetime.now(timezone.utc)
    if last_updated.tzinfo is None:
        last_updated = last_updated.replace(tzinfo=timezone.utc)

    age_hours = (now - last_updated).total_seconds() / 3600

    if age_hours > rule.max_hours:
        status = CheckStatus.FAILED
    elif age_hours > rule.max_hours * WARNING_THRESHOLD:
        status = CheckStatus.WARNING
    else:
        status = CheckStatus.PASSED

    if age_hours < 1:
        age_str = f"{int(age_hours * 60)} minutes ago"
    else:
        age_str = f"{age_hours:.1f} hours ago"

    return CheckResult(
        name="Freshness",
        status=status,
        message=f"{age_str} (threshold: < {rule.max_hours} hours)",
        actual_value=round(age_hours, 2),
        threshold=rule.max_hours,
    )
