"""Duplicate-rate check — what percentage of rows have a non-unique value?"""

from __future__ import annotations

from litmus.checks.runner import CheckResult, CheckStatus
from litmus.connectors.base import BaseConnector
from litmus.spec.metric_spec import DuplicateRule

WARNING_THRESHOLD = 0.9


def check_duplicate_rate(
    connector: BaseConnector,
    table: str,
    rule: DuplicateRule,
) -> CheckResult:
    """Report the duplicate rate for ``rule.column`` against ``rule.max_percentage``.

    Duplicate rate is defined as ``(total_rows - distinct_values) / total_rows * 100``.
    """
    name = f"Duplicate rate on {rule.column}"
    try:
        rate = connector.get_duplicate_rate(table, rule.column)
    except Exception as exc:
        return CheckResult(
            name=name,
            status=CheckStatus.ERROR,
            message=f"Could not query duplicate rate: {exc}",
            actual_value=None,
            threshold=f"< {rule.max_percentage}%",
        )

    if rule.max_percentage == 0:
        status = CheckStatus.PASSED if rate == 0 else CheckStatus.FAILED
        threshold_str = f"{rule.max_percentage}%"
    elif rate > rule.max_percentage:
        status = CheckStatus.FAILED
        threshold_str = f"< {rule.max_percentage}%"
    elif rate > rule.max_percentage * WARNING_THRESHOLD:
        status = CheckStatus.WARNING
        threshold_str = f"< {rule.max_percentage}%"
    else:
        status = CheckStatus.PASSED
        threshold_str = f"< {rule.max_percentage}%"

    return CheckResult(
        name=name,
        status=status,
        message=f"{rate:.2f}% (threshold: {threshold_str})",
        actual_value=round(rate, 2),
        threshold=rule.max_percentage,
    )
