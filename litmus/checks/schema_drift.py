"""Schema-drift check — compares current columns against the last recorded set."""

from __future__ import annotations

from litmus.checks.history import HistoryStore
from litmus.checks.runner import CheckResult, CheckStatus


def fingerprint(columns: list[str]) -> str:
    """Canonicalize a column list into a deterministic string.

    Sorted, case-folded, comma-joined. Comparison is order-insensitive so
    that a column reorder is not treated as drift.
    """
    return ",".join(sorted(c.lower() for c in columns))


def check_schema_drift(
    metric_name: str,
    current_columns: list[str] | None,
    history: HistoryStore | None,
) -> CheckResult:
    """Compare the current column list to the most recent recorded fingerprint.

    Returns ``PASSED`` on the first run for a metric (nothing to compare).
    Returns ``FAILED`` when the set of columns is different from the last run,
    with a human-readable diff listing added and removed columns.
    """
    name = "Schema drift"

    if history is None:
        return CheckResult(
            name=name,
            status=CheckStatus.PASSED,
            message="(history store disabled — pass --history to enable)",
            actual_value=None,
            threshold="no drift",
        )

    if current_columns is None:
        return CheckResult(
            name=name,
            status=CheckStatus.ERROR,
            message="Could not read columns from warehouse.",
            actual_value=None,
            threshold="no drift",
        )

    current_fp = fingerprint(current_columns)
    prior = history.last_record(metric_name)
    prior_fp = prior.schema_fingerprint if prior is not None else None

    if prior_fp is None:
        return CheckResult(
            name=name,
            status=CheckStatus.PASSED,
            message=f"{len(current_columns)} columns (no prior snapshot — warming up)",
            actual_value=current_fp,
            threshold="no drift",
        )

    if prior_fp == current_fp:
        return CheckResult(
            name=name,
            status=CheckStatus.PASSED,
            message=f"{len(current_columns)} columns, unchanged since last run",
            actual_value=current_fp,
            threshold="no drift",
        )

    current_set = set(current_fp.split(",")) if current_fp else set()
    prior_set = set(prior_fp.split(",")) if prior_fp else set()
    added = sorted(current_set - prior_set)
    removed = sorted(prior_set - current_set)
    parts = []
    if added:
        parts.append(f"+{', +'.join(added)}")
    if removed:
        parts.append(f"-{', -'.join(removed)}")
    diff = " ".join(parts) if parts else "(ordering only)"

    return CheckResult(
        name=name,
        status=CheckStatus.FAILED,
        message=f"columns changed: {diff}",
        actual_value=current_fp,
        threshold=prior_fp,
    )
