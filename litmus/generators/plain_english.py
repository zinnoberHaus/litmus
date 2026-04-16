"""Generate plain-English explanations from a MetricSpec."""

from __future__ import annotations

from litmus.spec.metric_spec import MetricSpec


def explain(spec: MetricSpec) -> str:
    """Generate a business-friendly explanation of a metric."""
    lines: list[str] = []

    lines.append(f"\U0001f4d6 {spec.name}")
    lines.append("")

    if spec.description:
        lines.append(spec.description)
        lines.append("")

    # Conditions
    includes = []
    excludes = []
    for cond in spec.conditions:
        lower = cond.lower()
        if any(kw in lower for kw in ["not", "exclude", "without"]):
            excludes.append(cond)
        else:
            includes.append(cond)

    if includes:
        lines.append("It includes:")
        for inc in includes:
            lines.append(f"  - {inc}")
    if excludes:
        lines.append("It excludes:")
        for exc in excludes:
            lines.append(f"  - {exc}")

    if includes or excludes:
        lines.append("")

    # Calculations
    if spec.calculations:
        lines.append("How it's calculated:")
        for i, calc in enumerate(spec.calculations, 1):
            lines.append(f"  {i}. {calc}")
        lines.append("")

    # Trust rules
    if spec.trust and spec.trust.total_checks > 0:
        lines.append("The data team checks this metric automatically to make sure:")
        if spec.trust.freshness:
            lines.append(
                f"  - The data is no more than"
                f" {spec.trust.freshness.max_hours:g} hours old"
            )
        for rule in spec.trust.null_rules:
            if rule.max_percentage == 0:
                lines.append(f"  - No {rule.column} values are missing")
            else:
                lines.append(
                    f"  - Less than {rule.max_percentage:g}%"
                    f" of {rule.column} values are missing"
                )
        for rule in spec.trust.volume_rules:
            table_note = f" in {rule.table}" if rule.table else ""
            lines.append(
                f"  - Row count{table_note} hasn't dropped more than "
                f"{rule.max_drop_percentage:g}% {rule.period} over {rule.period}"
            )
        for rule in spec.trust.range_rules:
            lines.append(
                f"  - The total is between"
                f" {rule.min_value:,.0f} and {rule.max_value:,.0f}"
            )
        for rule in spec.trust.change_rules:
            lines.append(
                f"  - It hasn't changed more than {rule.max_change_percentage:g}% "
                f"from last {rule.period}"
            )
        for dup_rule in spec.trust.duplicate_rules:
            if dup_rule.max_percentage == 0:
                lines.append(f"  - No {dup_rule.column} values are duplicated")
            else:
                lines.append(
                    f"  - Less than {dup_rule.max_percentage:g}% of"
                    f" {dup_rule.column} values are duplicated"
                )
        if spec.trust.schema_drift is not None:
            lines.append("  - The column list hasn't changed since the last run")
        for dist_rule in spec.trust.distribution_shift_rules:
            lines.append(
                f"  - The average {dist_rule.column} hasn't shifted more than "
                f"{dist_rule.max_change_percentage:g}%"
                f" {dist_rule.period} over {dist_rule.period}"
            )
        lines.append("")

    if spec.owner:
        lines.append(f"This metric is owned by {spec.owner}.")
        lines.append(f"If something looks wrong, contact: {spec.owner}")

    return "\n".join(lines)
