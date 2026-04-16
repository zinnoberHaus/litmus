"""Pretty CLI output using Rich."""

from __future__ import annotations

from rich.console import Console

from litmus.checks.runner import CheckStatus, CheckSuite
from litmus.spec.metric_spec import MetricSpec

_STATUS_ICONS = {
    CheckStatus.PASSED: "[green]\u2705[/green]",
    CheckStatus.WARNING: "[yellow]\u26a0\ufe0f [/yellow]",
    CheckStatus.FAILED: "[red]\u274c[/red]",
    CheckStatus.ERROR: "[red]\u2757[/red]",
}

_STATUS_SUFFIX = {
    CheckStatus.WARNING: " [yellow]— CLOSE TO LIMIT[/yellow]",
    CheckStatus.FAILED: " [red]— FAILED[/red]",
    CheckStatus.ERROR: " [red]— ERROR[/red]",
}


def print_header(console: Console) -> None:
    """Print the Litmus banner."""
    console.print()
    console.print("\U0001f9ea [bold]Litmus — Metric Trust Checker[/bold]")
    console.print("\u2501" * 40)


def print_metric_detail(
    console: Console,
    spec: MetricSpec,
    suite: CheckSuite,
) -> None:
    """Print detailed check results for a single metric."""
    console.print()
    console.print(f"\U0001f4ca [bold]{spec.name}[/bold]")
    if spec.owner:
        console.print(f"   Owner: {spec.owner}")
    if spec.description:
        console.print(f'   "{spec.description}"')
    console.print()
    console.print("   Trust Checks:")

    for result in suite.results:
        icon = _STATUS_ICONS.get(result.status, "  ")
        suffix = _STATUS_SUFFIX.get(result.status, "")
        console.print(f"   {icon} {result.name}: {result.message}{suffix}")

    score, total = suite.trust_score
    console.print()
    console.print(
        f"   Trust Score: {score:g}/{total}  {suite.health_indicator}"
    )
    console.print("   Last checked: just now")


def print_metric_summary(
    console: Console,
    spec: MetricSpec,
    suite: CheckSuite,
) -> None:
    """Print a one-line summary for a metric."""
    name = spec.name
    score_display = suite.trust_score_display
    indicator = suite.health_indicator
    dots = "." * max(1, 40 - len(name) - len(score_display))
    console.print(f"\U0001f4ca {name} {dots} {score_display}  {indicator}")


def print_footer(
    console: Console,
    suites: list[CheckSuite],
) -> None:
    """Print the summary footer."""
    total_metrics = len(suites)
    healthy = sum(1 for s in suites if s.failed == 0 and s.errors == 0 and s.warnings == 0)
    warning = sum(1 for s in suites if s.warnings > 0 and s.failed == 0 and s.errors == 0)
    failing = sum(1 for s in suites if s.failed > 0 or s.errors > 0)

    console.print()
    console.print("\u2501" * 40)
    parts = [f"{total_metrics} metric{'s' if total_metrics != 1 else ''} checked"]
    if healthy:
        parts.append(f"{healthy} healthy")
    if warning:
        parts.append(f"{warning} warning")
    if failing:
        parts.append(f"{failing} failing")
    console.print(" \u00b7 ".join(parts))


def report_verbose(
    console: Console,
    specs_and_suites: list[tuple[MetricSpec, CheckSuite]],
) -> None:
    """Full verbose output with details for each metric."""
    print_header(console)
    for spec, suite in specs_and_suites:
        print_metric_detail(console, spec, suite)
    print_footer(console, [s for _, s in specs_and_suites])
    console.print()


def report_summary(
    console: Console,
    specs_and_suites: list[tuple[MetricSpec, CheckSuite]],
) -> None:
    """One-line-per-metric summary output."""
    print_header(console)
    console.print()
    for spec, suite in specs_and_suites:
        print_metric_summary(console, spec, suite)
    print_footer(console, [s for _, s in specs_and_suites])
    console.print()
    if len(specs_and_suites) > 1:
        console.print("Run with --verbose for details.")
    console.print()
