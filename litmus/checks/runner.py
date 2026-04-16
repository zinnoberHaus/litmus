"""Orchestrate all trust checks for a metric spec."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum


class CheckStatus(Enum):
    PASSED = "passed"
    WARNING = "warning"
    FAILED = "failed"
    ERROR = "error"


@dataclass
class CheckResult:
    name: str
    status: CheckStatus
    message: str
    actual_value: object
    threshold: object
    details: dict | None = None


@dataclass
class CheckSuite:
    metric_name: str
    results: list[CheckResult] = field(default_factory=list)

    @property
    def passed(self) -> int:
        return sum(1 for r in self.results if r.status == CheckStatus.PASSED)

    @property
    def warnings(self) -> int:
        return sum(1 for r in self.results if r.status == CheckStatus.WARNING)

    @property
    def failed(self) -> int:
        return sum(1 for r in self.results if r.status == CheckStatus.FAILED)

    @property
    def errors(self) -> int:
        return sum(1 for r in self.results if r.status == CheckStatus.ERROR)

    @property
    def total(self) -> int:
        return len(self.results)

    @property
    def trust_score(self) -> tuple[float, int]:
        """Return (score, max) where warnings count as 0.5."""
        if not self.results:
            return (0, 0)
        score = 0.0
        for r in self.results:
            if r.status == CheckStatus.PASSED:
                score += 1.0
            elif r.status == CheckStatus.WARNING:
                score += 0.5
        return (score, len(self.results))

    @property
    def trust_score_display(self) -> str:
        score, total = self.trust_score
        return f"{score:g}/{total}"

    @property
    def health_indicator(self) -> str:
        if self.failed > 0 or self.errors > 0:
            return "\U0001f534"  # red circle
        if self.warnings > 0:
            return "\U0001f7e1"  # yellow circle
        return "\U0001f7e2"  # green circle


def run_checks(
    connector: BaseConnector,  # noqa: F821
    spec: MetricSpec,  # noqa: F821
    timestamp_column: str | None = None,
    value_column: str | None = None,
    history: HistoryStore | None = None,  # noqa: F821
    run_id: str | None = None,
    commit_sha: str | None = None,
) -> CheckSuite:
    """Run all trust checks defined in a MetricSpec and return results.

    Parameters
    ----------
    history
        Optional :class:`litmus.checks.history.HistoryStore`. When supplied,
        each run records the current metric value + row count so that future
        ``change_rules`` can compare against history. Pass ``None`` to disable
        (equivalent to ``litmus check --no-history``).
    """
    from litmus.checks.change import check_change
    from litmus.checks.distribution_shift import check_distribution_shift
    from litmus.checks.duplicate_rate import check_duplicate_rate
    from litmus.checks.freshness import check_freshness
    from litmus.checks.null_rate import check_null_rate
    from litmus.checks.range import check_range
    from litmus.checks.schema_drift import check_schema_drift, fingerprint
    from litmus.checks.volume import check_volume

    suite = CheckSuite(metric_name=spec.name)

    if spec.trust is None:
        return suite

    primary_table = spec.sources[0] if spec.sources else None
    if primary_table is None:
        return suite

    # Freshness
    if spec.trust.freshness:
        suite.results.append(
            check_freshness(connector, primary_table, spec.trust.freshness, timestamp_column)
        )

    # Null rates
    for rule in spec.trust.null_rules:
        suite.results.append(check_null_rate(connector, primary_table, rule))

    # Volume
    for rule in spec.trust.volume_rules:
        ts_col = timestamp_column or "updated_at"
        suite.results.append(check_volume(connector, primary_table, rule, ts_col))

    # Range (also yields the canonical "current value" we feed to change rules + history)
    v_col = value_column or "amount"
    current_value: float | None = None
    try:
        current_value = connector.get_column_sum(primary_table, v_col)
    except Exception:
        current_value = None

    for rule in spec.trust.range_rules:
        suite.results.append(check_range(connector, primary_table, v_col, rule))

    # Change rules — compare current value against history
    for rule in spec.trust.change_rules:
        suite.results.append(check_change(rule, spec.name, current_value, history))

    # Duplicate-rate rules — stateless, table + column
    for dup_rule in spec.trust.duplicate_rules:
        suite.results.append(check_duplicate_rate(connector, primary_table, dup_rule))

    # Schema drift — stateful, compares current columns against last run's snapshot
    current_columns: list[str] | None = None
    try:
        current_columns = connector.get_columns(primary_table)
    except Exception:
        current_columns = None

    if spec.trust.schema_drift is not None:
        suite.results.append(check_schema_drift(spec.name, current_columns, history))

    # Distribution shift — compares AVG(column) against history
    # Batch per-column means so we don't hit the warehouse twice for the same col.
    means: dict[str, float | None] = {}
    for dist_rule in spec.trust.distribution_shift_rules:
        if dist_rule.column not in means:
            try:
                means[dist_rule.column] = connector.get_column_mean(
                    primary_table, dist_rule.column
                )
            except Exception:
                means[dist_rule.column] = None
        suite.results.append(
            check_distribution_shift(
                dist_rule, spec.name, means[dist_rule.column], history
            )
        )

    # Record this run into history so the next run has something to compare.
    if history is not None:
        try:
            row_count = connector.get_row_count(primary_table)
        except Exception:
            row_count = None
        schema_fp = fingerprint(current_columns) if current_columns else None
        # ``means`` already holds the AVG for every column mentioned by a
        # distribution_shift rule above. Snapshot into history so the NEXT run
        # can compare against today.
        column_means: dict[str, float | None] = dict(means) if means else {}
        try:
            history.record(
                metric_name=spec.name,
                value_sum=current_value,
                row_count=row_count,
                run_id=run_id,
                commit_sha=commit_sha,
                schema_fingerprint=schema_fp,
                column_means=column_means,
            )
        except Exception:
            # Never let a history write break a check run.
            pass

    return suite
