"""Period-over-period change check — compares current value against history."""

from __future__ import annotations

from litmus.checks.history import HistoryStore
from litmus.checks.runner import CheckResult, CheckStatus
from litmus.spec.metric_spec import ChangeRule

WARNING_THRESHOLD = 0.9  # warn when within 90% of the limit


def check_change(
    rule: ChangeRule,
    metric_name: str,
    current_value: float | None,
    history: HistoryStore | None,
) -> CheckResult:
    """Compare ``current_value`` against the most recent value from ``rule.period`` ago.

    If no history store is configured, or no prior row exists for ``metric_name``
    at least one ``period`` old, the check returns ``PASSED`` with a message
    explaining history is still warming up — not ``ERROR``, because absence of
    history is the normal state for any new metric.
    """
    name = f"{rule.period.title()}-over-{rule.period} change"
    threshold = rule.max_change_percentage

    if history is None:
        return CheckResult(
            name=name,
            status=CheckStatus.PASSED,
            message=f"< {threshold}% (history store disabled — pass --history to enable)",
            actual_value=None,
            threshold=threshold,
        )

    if current_value is None:
        return CheckResult(
            name=name,
            status=CheckStatus.ERROR,
            message="Could not compute current value (NULL sum on primary source).",
            actual_value=None,
            threshold=threshold,
        )

    try:
        prior = history.previous_record(metric_name, rule.period)
    except ValueError as exc:
        return CheckResult(
            name=name,
            status=CheckStatus.ERROR,
            message=str(exc),
            actual_value=None,
            threshold=threshold,
        )

    if prior is None or prior.value_sum is None:
        return CheckResult(
            name=name,
            status=CheckStatus.PASSED,
            message=(
                f"< {threshold}% (no prior value from {rule.period} ago yet — "
                "history is still warming up)"
            ),
            actual_value=None,
            threshold=threshold,
        )

    if prior.value_sum == 0:
        return CheckResult(
            name=name,
            status=CheckStatus.WARNING,
            message=f"prior value was 0; current {current_value:g} — can't compute % change",
            actual_value=current_value,
            threshold=threshold,
        )

    change_pct = ((current_value - prior.value_sum) / abs(prior.value_sum)) * 100
    abs_change = abs(change_pct)

    if abs_change > threshold:
        status = CheckStatus.FAILED
    elif abs_change > threshold * WARNING_THRESHOLD:
        status = CheckStatus.WARNING
    else:
        status = CheckStatus.PASSED

    return CheckResult(
        name=name,
        status=status,
        message=(
            f"{change_pct:+.1f}% vs {prior.recorded_at.date().isoformat()} "
            f"(threshold: < {threshold}%)"
        ),
        actual_value=round(change_pct, 2),
        threshold=threshold,
    )
