"""Markdown output reporter."""

from __future__ import annotations

from datetime import datetime, timezone

from litmus.checks.runner import CheckStatus, CheckSuite
from litmus.spec.metric_spec import MetricSpec

_STATUS_EMOJI = {
    CheckStatus.PASSED: "pass",
    CheckStatus.WARNING: "warn",
    CheckStatus.FAILED: "FAIL",
    CheckStatus.ERROR: "ERR",
}


def generate_markdown_report(
    specs_and_suites: list[tuple[MetricSpec, CheckSuite]],
) -> str:
    """Generate a Markdown report string."""
    lines: list[str] = []
    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")

    lines.append("# Litmus Trust Report")
    lines.append(f"\nGenerated: {now}\n")

    # Summary table
    lines.append("## Summary\n")
    lines.append("| Metric | Score | Status |")
    lines.append("|--------|-------|--------|")
    for spec, suite in specs_and_suites:
        score_display = suite.trust_score_display
        if suite.failed > 0 or suite.errors > 0:
            status = "Failing"
        elif suite.warnings > 0:
            status = "Warning"
        else:
            status = "Healthy"
        lines.append(f"| {spec.name} | {score_display} | {status} |")

    # Details
    lines.append("\n## Details\n")
    for spec, suite in specs_and_suites:
        lines.append(f"### {spec.name}\n")
        if spec.description:
            lines.append(f"> {spec.description}\n")
        if spec.owner:
            lines.append(f"**Owner:** {spec.owner}\n")
        if spec.tags:
            lines.append(f"**Tags:** {', '.join(spec.tags)}\n")

        lines.append("| Check | Status | Details |")
        lines.append("|-------|--------|---------|")
        for r in suite.results:
            status_label = _STATUS_EMOJI[r.status]
            lines.append(f"| {r.name} | {status_label} | {r.message} |")

        score, total = suite.trust_score
        lines.append(f"\n**Trust Score:** {score:g}/{total}\n")

    # Footer
    total = len(specs_and_suites)
    healthy = sum(
        1 for _, s in specs_and_suites
        if s.failed == 0 and s.errors == 0 and s.warnings == 0
    )
    warning = sum(1 for _, s in specs_and_suites if s.warnings > 0 and s.failed == 0)
    failing = sum(1 for _, s in specs_and_suites if s.failed > 0 or s.errors > 0)
    lines.append("---")
    lines.append(
        f"\n{total} metrics checked | {healthy} healthy"
        f" | {warning} warning | {failing} failing"
    )

    return "\n".join(lines)
