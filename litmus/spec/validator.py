"""Validate that a MetricSpec is complete enough to run checks."""

from __future__ import annotations

from dataclasses import dataclass, field

from litmus.spec.metric_spec import MetricSpec


@dataclass
class ValidationResult:
    valid: bool
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)


def validate_spec(spec: MetricSpec) -> ValidationResult:
    """Check that a MetricSpec has all required fields for running trust checks."""
    errors: list[str] = []
    warnings: list[str] = []

    if not spec.name:
        errors.append("Metric name is required.")

    if not spec.sources:
        errors.append("At least one source table is required.")

    if not spec.conditions:
        warnings.append("No conditions defined in the Given block.")

    if not spec.calculations:
        warnings.append("No calculations defined in the When block.")

    if spec.trust is None:
        warnings.append("No Trust block defined — no checks will run.")
    elif spec.trust.total_checks == 0:
        warnings.append("Trust block is empty — no checks will run.")

    return ValidationResult(
        valid=len(errors) == 0,
        errors=errors,
        warnings=warnings,
    )
