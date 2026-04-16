"""Value range check — is the metric value within expected bounds?"""

from __future__ import annotations

from litmus.checks.runner import CheckResult, CheckStatus
from litmus.connectors.base import BaseConnector
from litmus.spec.metric_spec import RangeRule


def check_range(
    connector: BaseConnector,
    table: str,
    column: str,
    rule: RangeRule,
) -> CheckResult:
    """Check that the computed metric value falls within the expected range."""
    try:
        value = connector.get_column_sum(table, column)
    except Exception as exc:
        return CheckResult(
            name="Value range",
            status=CheckStatus.ERROR,
            message=f"Could not query value: {exc}",
            actual_value=None,
            threshold=f"{rule.min_value:,.0f} – {rule.max_value:,.0f}",
        )

    if value is None:
        return CheckResult(
            name="Value range",
            status=CheckStatus.ERROR,
            message="No value returned (NULL).",
            actual_value=None,
            threshold=f"{rule.min_value:,.0f} – {rule.max_value:,.0f}",
        )

    if value < rule.min_value or value > rule.max_value:
        status = CheckStatus.FAILED
    else:
        # Warn if within 10% of either boundary
        range_size = rule.max_value - rule.min_value
        margin = range_size * 0.1
        if value < rule.min_value + margin or value > rule.max_value - margin:
            status = CheckStatus.WARNING
        else:
            status = CheckStatus.PASSED

    return CheckResult(
        name="Value range",
        status=status,
        message=f"{value:,.2f} (range: {rule.min_value:,.0f} – {rule.max_value:,.0f})",
        actual_value=value,
        threshold=f"{rule.min_value} – {rule.max_value}",
    )
