"""Distribution-shift check — compares the current column mean against history."""

from __future__ import annotations

from litmus.checks.history import HistoryStore
from litmus.checks.runner import CheckResult, CheckStatus
from litmus.spec.metric_spec import DistributionShiftRule

WARNING_THRESHOLD = 0.9


def check_distribution_shift(
    rule: DistributionShiftRule,
    metric_name: str,
    current_mean: float | None,
    history: HistoryStore | None,
) -> CheckResult:
    """Report the relative change of ``AVG(column)`` against a prior record.

    Uses the same ``period`` semantics as ``ChangeRule``: look up the most
    recent history row at least ``period`` old. Returns ``PASSED`` when no
    prior row exists (the metric is still warming up), ``ERROR`` when the
    current mean can't be computed.
    """
    name = f"{rule.period.title()}-over-{rule.period} mean shift ({rule.column})"
    threshold = rule.max_change_percentage

    if history is None:
        return CheckResult(
            name=name,
            status=CheckStatus.PASSED,
            message=f"< {threshold}% (history store disabled — pass --history to enable)",
            actual_value=None,
            threshold=threshold,
        )

    if current_mean is None:
        return CheckResult(
            name=name,
            status=CheckStatus.ERROR,
            message=f"Could not compute mean({rule.column}) on primary source.",
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

    prior_mean = prior.column_means.get(rule.column) if prior is not None else None
    if prior is None or prior_mean is None:
        return CheckResult(
            name=name,
            status=CheckStatus.PASSED,
            message=(
                f"< {threshold}% (no prior mean from {rule.period} ago yet — "
                "history is still warming up)"
            ),
            actual_value=None,
            threshold=threshold,
        )

    if prior_mean == 0:
        return CheckResult(
            name=name,
            status=CheckStatus.WARNING,
            message=(
                f"prior mean was 0; current {current_mean:g} — "
                "can't compute % shift"
            ),
            actual_value=current_mean,
            threshold=threshold,
        )

    change_pct = ((current_mean - prior_mean) / abs(prior_mean)) * 100
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
