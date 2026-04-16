"""CLI entry point using Click."""

from __future__ import annotations

import sys
from pathlib import Path

import click
from rich.console import Console

from litmus import __version__

console = Console()


@click.group()
@click.version_option(version=__version__, prog_name="litmus")
def main():
    """Litmus — BDD-style metric definitions with built-in data trust checks."""


# ── litmus check ────────────────────────────────────────────────────


@main.command()
@click.argument("path")
@click.option("--config", "-c", default=None, help="Path to litmus.yml config file.")
@click.option("--verbose", "-v", is_flag=True, help="Show detailed check results.")
@click.option(
    "--format", "-f", "output_format",
    type=click.Choice(["console", "json", "html", "markdown"]),
    default=None,
    help="Output format (overrides config).",
)
@click.option("--output", "-o", default=None, help="Write report to file.")
@click.option(
    "--schema-version",
    default="v1",
    help="JSON schema version for --format json (currently only 'v1' is supported).",
)
@click.option(
    "--no-history",
    is_flag=True,
    default=False,
    help="Skip writes to the SQLite history store (disables change_rule comparisons).",
)
@click.option(
    "--history-db",
    default=None,
    help="Path to the SQLite history DB. Defaults to ~/.litmus/history.db or $LITMUS_HISTORY_DB.",
)
def check(
    path: str,
    config: str | None,
    verbose: bool,
    output_format: str | None,
    output: str | None,
    schema_version: str,
    no_history: bool,
    history_db: str | None,
):
    """Run trust checks against a .metric file or directory."""
    from litmus.checks.runner import run_checks
    from litmus.config.settings import get_connector, load_config
    from litmus.parser import parse_metric_file
    from litmus.reporters.console import report_summary, report_verbose
    from litmus.reporters.html_reporter import generate_html_report
    from litmus.reporters.json_reporter import generate_json_report
    from litmus.reporters.markdown_reporter import generate_markdown_report

    cfg = load_config(config)
    fmt = output_format or cfg.reporting.format

    target = Path(path)
    if target.is_file():
        metric_files = [target]
    elif target.is_dir():
        metric_files = sorted(target.glob("*.metric"))
        if not metric_files:
            console.print(f"[red]No .metric files found in {target}[/red]")
            sys.exit(1)
    else:
        console.print(f"[red]Path not found: {path}[/red]")
        sys.exit(1)

    # Parse all metric files
    specs = []
    for mf in metric_files:
        try:
            spec = parse_metric_file(mf)
            specs.append(spec)
        except Exception as exc:
            console.print(f"[red]Error parsing {mf}: {exc}[/red]")
            sys.exit(1)

    # Run checks
    import os as _os

    from litmus.checks.history import HistoryStore

    connector = get_connector(cfg)
    history = None if no_history else HistoryStore(path=history_db)
    if history is not None:
        history.connect()
    try:
        connector.connect()
        run_id = _os.environ.get("GITHUB_RUN_ID") or _os.environ.get("LITMUS_RUN_ID")
        commit_sha = _os.environ.get("GITHUB_SHA") or _os.environ.get("LITMUS_COMMIT_SHA")
        results = []
        for spec in specs:
            suite = run_checks(
                connector,
                spec,
                history=history,
                run_id=run_id,
                commit_sha=commit_sha,
            )
            results.append((spec, suite))
    finally:
        connector.close()
        if history is not None:
            history.close()

    # Output
    if fmt == "json":
        report = generate_json_report(results, schema_version=schema_version)
        if output:
            Path(output).write_text(report)
            console.print(f"Report written to {output}")
        else:
            click.echo(report)
    elif fmt == "html":
        report = generate_html_report(results)
        if output:
            Path(output).write_text(report)
            console.print(f"Report written to {output}")
        else:
            click.echo(report)
    elif fmt == "markdown":
        report = generate_markdown_report(results)
        if output:
            Path(output).write_text(report)
            console.print(f"Report written to {output}")
        else:
            click.echo(report)
    else:
        if verbose or len(results) == 1:
            report_verbose(console, results)
        else:
            report_summary(console, results)

    # Exit code
    any_failed = any(suite.failed > 0 or suite.errors > 0 for _, suite in results)
    sys.exit(1 if any_failed else 0)


# ── litmus parse ────────────────────────────────────────────────────


@main.command()
@click.argument("file")
def parse(file: str):
    """Parse a .metric file and display the structured output."""
    from litmus.parser import parse_metric_file

    try:
        spec = parse_metric_file(file)
    except Exception as exc:
        console.print(f"[red]Parse error: {exc}[/red]")
        sys.exit(1)

    console.print()
    console.print("[bold]Parsed MetricSpec:[/bold]")
    console.print(f"  name: {spec.name}")
    console.print(f"  description: {spec.description}")
    console.print(f"  owner: {spec.owner}")
    console.print(f"  tags: {spec.tags}")
    console.print(f"  sources: {spec.sources}")
    console.print(f"  conditions: {spec.conditions}")
    console.print(f"  calculations: {spec.calculations}")
    console.print(f"  result_name: {spec.result_name}")

    if spec.trust:
        console.print("  trust_rules:")
        if spec.trust.freshness:
            console.print(f"    - freshness: < {spec.trust.freshness.max_hours} hours")
        for rule in spec.trust.null_rules:
            console.print(f"    - null_rate({rule.column}): < {rule.max_percentage}%")
        for rule in spec.trust.volume_rules:
            table = f"({rule.table})" if rule.table else ""
            console.print(
                f"    - volume_change{table}"
                f"({rule.period}): < {rule.max_drop_percentage}%"
            )
        for rule in spec.trust.range_rules:
            console.print(f"    - value_range: [{rule.min_value}, {rule.max_value}]")
        for rule in spec.trust.change_rules:
            console.print(f"    - value_change({rule.period}): < {rule.max_change_percentage}%")
        for dup_rule in spec.trust.duplicate_rules:
            console.print(
                f"    - duplicate_rate({dup_rule.column}):"
                f" < {dup_rule.max_percentage}%"
            )
        if spec.trust.schema_drift is not None:
            console.print("    - schema_drift: forbidden")
        for dist_rule in spec.trust.distribution_shift_rules:
            console.print(
                f"    - distribution_shift({dist_rule.column}, {dist_rule.period}):"
                f" < {dist_rule.max_change_percentage}%"
            )
    console.print()


# ── litmus explain ──────────────────────────────────────────────────


@main.command()
@click.argument("file")
def explain(file: str):
    """Generate a plain-English explanation of a metric."""
    from litmus.generators.plain_english import explain as do_explain
    from litmus.parser import parse_metric_file

    try:
        spec = parse_metric_file(file)
    except Exception as exc:
        console.print(f"[red]Parse error: {exc}[/red]")
        sys.exit(1)

    console.print()
    console.print(do_explain(spec))
    console.print()


# ── litmus init ─────────────────────────────────────────────────────


_EXAMPLE_CONFIG = """\
# litmus.yml
version: 1

# Where your .metric files live
metrics_dir: metrics/

# Warehouse connection
warehouse:
  type: duckdb  # duckdb | postgres | snowflake | bigquery
  database: ":memory:"
  # For real warehouses, set credentials via env vars:
  # LITMUS_WAREHOUSE_USER
  # LITMUS_WAREHOUSE_PASSWORD

# Check defaults (can be overridden per metric)
defaults:
  freshness: 24 hours
  null_rate: 5%
  volume_change: 25%

# Output
reporting:
  format: console  # console | json | html | markdown
  colors: true
"""

_EXAMPLE_METRIC = """\
Metric: Example Revenue
Description: Total revenue from completed orders in the current calendar month
Owner: data-team
Tags: finance, example

Source: orders

Given all records from orders table
  And status is "completed"
  And order_date is within current calendar month

When we calculate
  Then sum the amount column
  And round to 2 decimal places

The result is "Example Revenue"

Trust:
  Freshness must be less than 24 hours
  Null rate on amount must be less than 5%
  Row count must not drop more than 25% day over day
  Value must be between 0 and 10000000
"""


@main.command()
def init():
    """Initialize a new litmus project with example files."""
    config_path = Path("litmus.yml")
    metrics_dir = Path("metrics")

    created = []

    if not config_path.exists():
        config_path.write_text(_EXAMPLE_CONFIG)
        created.append("litmus.yml          — configuration file")
    else:
        console.print("[yellow]litmus.yml already exists, skipping.[/yellow]")

    metrics_dir.mkdir(exist_ok=True)
    created.append("metrics/            — directory for .metric files")

    example_path = metrics_dir / "example.metric"
    if not example_path.exists():
        example_path.write_text(_EXAMPLE_METRIC)
        created.append("metrics/example.metric — example metric spec")
    else:
        console.print("[yellow]metrics/example.metric already exists, skipping.[/yellow]")

    console.print()
    console.print("[bold]Created:[/bold]")
    for item in created:
        console.print(f"  {item}")
    console.print()
    console.print("Edit litmus.yml to configure your warehouse connection.")
    console.print("Run [bold]litmus check metrics/[/bold] to validate your metrics.")
    console.print()


# ── litmus import-dbt ───────────────────────────────────────────────


@main.command("import-dbt")
@click.argument("manifest_path")
@click.option(
    "--output-dir", "-o", default="metrics",
    help="Directory for generated .metric files.",
)
def import_dbt(manifest_path: str, output_dir: str):
    """Import metric definitions from a dbt manifest.json."""
    from litmus.generators.dbt_importer import generate_metric_file, import_dbt_manifest

    manifest = Path(manifest_path)
    if not manifest.exists():
        console.print(f"[red]File not found: {manifest_path}[/red]")
        sys.exit(1)

    try:
        specs = import_dbt_manifest(manifest)
    except Exception as exc:
        console.print(f"[red]Error reading manifest: {exc}[/red]")
        sys.exit(1)

    if not specs:
        console.print("[yellow]No metrics or models found in the manifest.[/yellow]")
        sys.exit(0)

    out_dir = Path(output_dir)
    out_dir.mkdir(exist_ok=True)

    console.print(f"\nFound {len(specs)} metrics in dbt manifest.")
    console.print("Generated:")

    for spec in specs:
        filename = spec.name.lower().replace(" ", "_") + ".metric"
        file_path = out_dir / filename
        file_path.write_text(generate_metric_file(spec))
        console.print(f"  {file_path}")

    console.print()
    console.print("Review and edit each file to add Trust rules and plain-English descriptions.")
    console.print()


# ── litmus share ────────────────────────────────────────────────────


@main.command()
@click.argument("path")
@click.option(
    "--output-dir", "-o", default="litmus-share",
    help="Directory for generated HTML. Default: ./litmus-share/",
)
@click.option(
    "--output", default=None,
    help="Single-file output path (overrides --output-dir).",
)
@click.option(
    "--config", "-c", default=None, help="Path to litmus.yml config file.",
)
@click.option(
    "--no-run",
    is_flag=True,
    default=False,
    help="Skip running checks — render the metric definition only.",
)
def share(
    path: str,
    output_dir: str,
    output: str | None,
    config: str | None,
    no_run: bool,
):
    """Render a .metric file as a single-file HTML artifact for non-engineers."""
    from litmus.checks.runner import run_checks
    from litmus.config.settings import get_connector, load_config
    from litmus.generators.share_html import generate_share_html
    from litmus.parser import parse_metric_file

    target = Path(path)
    if target.is_file():
        metric_files = [target]
    elif target.is_dir():
        metric_files = sorted(target.glob("*.metric"))
        if not metric_files:
            console.print(f"[red]No .metric files found in {target}[/red]")
            sys.exit(1)
    else:
        console.print(f"[red]Path not found: {path}[/red]")
        sys.exit(1)

    if output and len(metric_files) > 1:
        console.print(
            "[red]--output takes a single file path; use --output-dir for"
            " multiple metrics.[/red]"
        )
        sys.exit(1)

    specs = []
    for mf in metric_files:
        try:
            specs.append(parse_metric_file(mf))
        except Exception as exc:
            console.print(f"[red]Error parsing {mf}: {exc}[/red]")
            sys.exit(1)

    suites: dict[str, object] = {}
    if not no_run:
        cfg = load_config(config)
        connector = get_connector(cfg)
        try:
            connector.connect()
            for spec in specs:
                try:
                    suites[spec.name] = run_checks(connector, spec)
                except Exception as exc:
                    console.print(
                        f"[yellow]Warning: failed to run checks for"
                        f" {spec.name}: {exc}[/yellow]"
                    )
        finally:
            connector.close()

    if output:
        out_path = Path(output)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        html = generate_share_html(specs[0], suites.get(specs[0].name))  # type: ignore[arg-type]
        out_path.write_text(html)
        console.print(f"Share artifact written to [bold]{out_path}[/bold]")
        return

    out_dir = Path(output_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    written: list[Path] = []
    for spec in specs:
        slug = spec.name.lower().replace(" ", "_")
        slug = "".join(ch for ch in slug if ch.isalnum() or ch == "_")
        filename = f"{slug}.html"
        html = generate_share_html(spec, suites.get(spec.name))  # type: ignore[arg-type]
        file_path = out_dir / filename
        file_path.write_text(html)
        written.append(file_path)

    console.print()
    console.print(f"[bold]Share artifacts written to {out_dir}/[/bold]")
    for p in written:
        console.print(f"  {p}")
    console.print()


# ── litmus export ───────────────────────────────────────────────────


@main.command("export")
@click.argument("path")
@click.option(
    "--to", "target",
    type=click.Choice(["dbt"]),
    required=True,
    help="Export target. Only 'dbt' is supported today.",
)
@click.option(
    "--output-dir", "-o", default=".",
    help="Directory to write generated artifacts into.",
)
def export(path: str, target: str, output_dir: str):
    """Export a .metric file (or directory) to an external tool's format."""
    from litmus.generators.dbt_exporter import export_to_dbt
    from litmus.parser import parse_metric_file

    target_path = Path(path)
    if target_path.is_file():
        metric_files = [target_path]
    elif target_path.is_dir():
        metric_files = sorted(target_path.glob("*.metric"))
        if not metric_files:
            console.print(f"[red]No .metric files found in {target_path}[/red]")
            sys.exit(1)
    else:
        console.print(f"[red]Path not found: {path}[/red]")
        sys.exit(1)

    out_dir = Path(output_dir)
    models_dir = out_dir / "models" / "litmus"
    tests_dir = out_dir / "tests" / "singular"
    mapping_dir = out_dir / ".litmus"
    for d in (models_dir, tests_dir, mapping_dir):
        d.mkdir(parents=True, exist_ok=True)

    written: list[Path] = []
    for mf in metric_files:
        try:
            spec = parse_metric_file(mf)
        except Exception as exc:
            console.print(f"[red]Error parsing {mf}: {exc}[/red]")
            sys.exit(1)

        bundle = export_to_dbt(spec)
        model_path = models_dir / bundle.model_filename
        test_path = tests_dir / bundle.test_filename
        mapping_path = mapping_dir / bundle.mapping_filename

        model_path.write_text(bundle.model_yaml)
        test_path.write_text(bundle.singular_test_sql)
        mapping_path.write_text(bundle.mapping_markdown)
        written.extend([model_path, test_path, mapping_path])

    console.print()
    console.print(f"[bold]Exported {len(metric_files)} metric(s) to {target}:[/bold]")
    for p in written:
        console.print(f"  {p}")
    console.print()
    console.print(
        "Review the mapping doc in [cyan].litmus/[/cyan] — rules marked TODO"
        " still need `litmus check` in CI."
    )
    console.print()


# ── litmus report ───────────────────────────────────────────────────


@main.command()
@click.argument("directory")
@click.option(
    "--format", "-f", "output_format",
    type=click.Choice(["html", "markdown", "json"]),
    default="html",
    help="Report format.",
)
@click.option("--output", "-o", default=None, help="Output file path.")
@click.option("--config", "-c", default=None, help="Path to litmus.yml config file.")
def report(directory: str, output_format: str, output: str | None, config: str | None):
    """Generate a full trust report for all metrics in a directory."""
    from litmus.checks.runner import run_checks
    from litmus.config.settings import get_connector, load_config
    from litmus.parser import parse_metric_file
    from litmus.reporters.html_reporter import generate_html_report
    from litmus.reporters.json_reporter import generate_json_report
    from litmus.reporters.markdown_reporter import generate_markdown_report

    cfg = load_config(config)
    target = Path(directory)

    metric_files = sorted(target.glob("*.metric"))
    if not metric_files:
        console.print(f"[red]No .metric files found in {target}[/red]")
        sys.exit(1)

    specs = []
    for mf in metric_files:
        try:
            specs.append(parse_metric_file(mf))
        except Exception as exc:
            console.print(f"[red]Error parsing {mf}: {exc}[/red]")
            sys.exit(1)

    connector = get_connector(cfg)
    try:
        connector.connect()
        results = [(spec, run_checks(connector, spec)) for spec in specs]
    finally:
        connector.close()

    generators = {
        "html": generate_html_report,
        "markdown": generate_markdown_report,
        "json": generate_json_report,
    }
    report_content = generators[output_format](results)

    if output:
        Path(output).write_text(report_content)
        console.print(f"Report written to {output}")
    else:
        click.echo(report_content)


if __name__ == "__main__":
    main()
