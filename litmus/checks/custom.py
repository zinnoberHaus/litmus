"""Custom SQL check — run arbitrary SQL and evaluate the result."""

from __future__ import annotations

from litmus.checks.runner import CheckResult, CheckStatus
from litmus.connectors.base import BaseConnector


def check_custom_sql(
    connector: BaseConnector,
    sql: str,
    name: str = "Custom SQL",
    expected_value: float | None = None,
    min_value: float | None = None,
    max_value: float | None = None,
) -> CheckResult:
    """Run a custom SQL query and evaluate the scalar result."""
    try:
        rows = connector.execute_query(sql)
    except Exception as exc:
        return CheckResult(
            name=name,
            status=CheckStatus.ERROR,
            message=f"Query failed: {exc}",
            actual_value=None,
            threshold=None,
        )

    if not rows:
        return CheckResult(
            name=name,
            status=CheckStatus.ERROR,
            message="Query returned no rows.",
            actual_value=None,
            threshold=None,
        )

    # Take the first column of the first row as the scalar result
    first_row = rows[0]
    value = list(first_row.values())[0]

    if expected_value is not None:
        status = CheckStatus.PASSED if value == expected_value else CheckStatus.FAILED
        threshold = f"== {expected_value}"
    elif min_value is not None and max_value is not None:
        status = CheckStatus.PASSED if min_value <= value <= max_value else CheckStatus.FAILED
        threshold = f"{min_value} – {max_value}"
    else:
        status = CheckStatus.PASSED
        threshold = None

    return CheckResult(
        name=name,
        status=status,
        message=f"Result: {value}",
        actual_value=value,
        threshold=threshold,
    )
