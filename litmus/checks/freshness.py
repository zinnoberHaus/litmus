"""Data freshness check — how recently was the source table updated?"""

from __future__ import annotations

from datetime import datetime, timezone

from litmus.checks.runner import CheckResult, CheckStatus
from litmus.connectors.base import BaseConnector
from litmus.spec.metric_spec import FreshnessRule

WARNING_THRESHOLD = 0.9  # warn when within 90% of the limit


def _format_duration(hours: float) -> str:
    """Render an hours value using whichever unit reads naturally."""
    if hours < 1:
        minutes = max(1, int(round(hours * 60)))
        return f"{minutes} minute{'s' if minutes != 1 else ''}"
    if hours < 24:
        return f"{hours:g} hour{'s' if hours != 1 else ''}"
    days = hours / 24
    return f"{days:g} day{'s' if days != 1 else ''}"


def check_freshness(
    connector: BaseConnector,
    table: str,
    rule: FreshnessRule,
    timestamp_column: str | None = None,
) -> CheckResult:
    """Check that the source table was updated within the freshness window."""
    threshold_str = f"< {_format_duration(rule.max_hours)}"
    try:
        last_updated = connector.get_table_freshness(table, timestamp_column)
    except Exception as exc:
        return CheckResult(
            name="Freshness",
            status=CheckStatus.ERROR,
            message=f"Could not query freshness: {exc}",
            actual_value=None,
            threshold=threshold_str,
        )

    if last_updated is None:
        return CheckResult(
            name="Freshness",
            status=CheckStatus.ERROR,
            message="No timestamp data found in table.",
            actual_value=None,
            threshold=threshold_str,
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

    age_str = f"{_format_duration(age_hours)} ago"

    return CheckResult(
        name="Freshness",
        status=status,
        message=f"{age_str} (threshold: {threshold_str})",
        actual_value=round(age_hours, 2),
        threshold=rule.max_hours,
    )
