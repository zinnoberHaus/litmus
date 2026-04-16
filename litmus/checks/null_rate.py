"""Null rate check — what percentage of a column's values are NULL?"""

from __future__ import annotations

from litmus.checks.runner import CheckResult, CheckStatus
from litmus.connectors.base import BaseConnector
from litmus.spec.metric_spec import NullRule

WARNING_THRESHOLD = 0.9  # warn when within 90% of the limit


def check_null_rate(
    connector: BaseConnector,
    table: str,
    rule: NullRule,
) -> CheckResult:
    """Check that the null rate for a column is within the threshold."""
    try:
        null_rate = connector.get_null_rate(table, rule.column)
    except Exception as exc:
        return CheckResult(
            name=f"Null rate on {rule.column}",
            status=CheckStatus.ERROR,
            message=f"Could not query null rate: {exc}",
            actual_value=None,
            threshold=f"< {rule.max_percentage}%",
        )

    if rule.max_percentage == 0:
        # Exact zero required
        status = CheckStatus.PASSED if null_rate == 0 else CheckStatus.FAILED
    elif null_rate > rule.max_percentage:
        status = CheckStatus.FAILED
    elif null_rate > rule.max_percentage * WARNING_THRESHOLD:
        status = CheckStatus.WARNING
    else:
        status = CheckStatus.PASSED

    if rule.max_percentage == 0:
        threshold_str = f"{rule.max_percentage}%"
    else:
        threshold_str = f"< {rule.max_percentage}%"

    return CheckResult(
        name=f"Null rate on {rule.column}",
        status=status,
        message=f"{null_rate:.1f}% (threshold: {threshold_str})",
        actual_value=round(null_rate, 2),
        threshold=rule.max_percentage,
    )
