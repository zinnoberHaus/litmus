"""CLI entry point using Click."""

from __future__ import annotations

import sys
from pathlib import Path

import click
from rich.console import Console

from litmus import __version__

console = Console()


def _detect_dbt_project(start: Path | None = None) -> bool:
    """Return True if a ``dbt_project.yml`` lives in ``start`` or any ancestor.

    Used by ``--backend auto`` per blueprint Decision 2. Walks up to the
    filesystem root. No I/O beyond ``Path.exists()``.
    """
    cur = (start or Path.cwd()).resolve()
    for parent in (cur, *cur.parents):
        if (parent / "dbt_project.yml").is_file():
            return True
    return False


@click.group()
@click.version_option(version=__version__, prog_name="litmus")
def main():
    """Litmus — canonical metric contracts with built-in data trust checks.

    \b
    Three audiences, one spec:
      engineers  — .metric / YAML contracts, run via CLI, dbt package, or CI
      PMs        — Slack sign-off + /ask (v0.3)
      everyone   — embeddable trust badges
    """


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
    help="Skip writes to the history store (disables change_rule comparisons).",
)
@click.option(
    "--history-db",
    default=None,
    help="Path to the SQLite history DB. Defaults to ~/.litmus/history.db or $LITMUS_HISTORY_DB.",
)
@click.option(
    "--backend",
    type=click.Choice(["sqlite", "warehouse", "auto"]),
    default="auto",
    help=(
        "History backend. 'sqlite' = local ~/.litmus/history.db (default for "
        "solo use). 'warehouse' = shared litmus_history table in the configured "
        "warehouse (shared across a team). 'auto' picks 'warehouse' when a dbt "
        "project is detected or $LITMUS_BACKEND=warehouse is set, else 'sqlite'."
    ),
)
@click.option(
    "--history-schema",
    default=None,
    help=(
        "Schema (a.k.a. dataset) to hold the litmus_history table when "
        "--backend warehouse. Defaults to the warehouse's configured schema."
    ),
)
@click.option(
    "--push",
    "push_endpoint",
    default=None,
    help="Push results to a Litmus server (URL). Falls back to $LITMUS_ENDPOINT.",
)
@click.option(
    "--api-key",
    "api_key",
    default=None,
    help="API key for --push. Falls back to $LITMUS_API_KEY.",
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
    backend: str,
    history_schema: str | None,
    push_endpoint: str | None,
    api_key: str | None,
):
    """Run trust checks against a .metric (or YAML) file or directory."""
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

    from litmus.checks.history import HistoryStore, WarehouseHistoryStore

    connector = get_connector(cfg)

    # Resolve --backend auto → sqlite or warehouse per blueprint Decision 2.
    effective_backend = backend
    if backend == "auto":
        if _detect_dbt_project() or _os.environ.get("LITMUS_BACKEND") == "warehouse":
            effective_backend = "warehouse"
        else:
            effective_backend = "sqlite"

    history: object | None
    if no_history:
        history = None
    elif effective_backend == "warehouse":
        # WarehouseHistoryStore piggy-backs on the same connector run_checks
        # already opens, so we don't pay a second connection.
        history = WarehouseHistoryStore(
            connector=connector,
            schema=history_schema or (cfg.warehouse.schema if cfg.warehouse.schema else None),
        )
    else:
        history = HistoryStore(path=history_db)

    try:
        connector.connect()
        # WarehouseHistoryStore needs the connector open before ``connect()``.
        if history is not None:
            history.connect()  # type: ignore[union-attr]
        run_id = _os.environ.get("GITHUB_RUN_ID") or _os.environ.get("LITMUS_RUN_ID")
        commit_sha = _os.environ.get("GITHUB_SHA") or _os.environ.get("LITMUS_COMMIT_SHA")
        results = []
        for spec in specs:
            suite = run_checks(
                connector,
                spec,
                history=history,  # type: ignore[arg-type]
                run_id=run_id,
                commit_sha=commit_sha,
            )
            results.append((spec, suite))
    finally:
        if history is not None:
            history.close()  # type: ignore[union-attr]
        connector.close()

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

    # Push results to hosted Litmus if configured (CLI flag or env var).
    from litmus.api_push import PushConfig, PushError, push_results, read_spec_texts

    push_cfg = PushConfig.from_env(endpoint=push_endpoint, api_key=api_key)
    if push_cfg is not None:
        try:
            spec_texts = read_spec_texts(metric_files, {s.name: s for s in specs})
            metric_ids = push_results(push_cfg, results, spec_texts=spec_texts)
            console.print(
                f"[dim]Pushed {len(metric_ids)} metric(s) to {push_cfg.endpoint}[/dim]"
            )
        except PushError as exc:
            console.print(f"[yellow]Push failed: {exc}[/yellow]")

    # Exit code
    any_failed = any(suite.failed > 0 or suite.errors > 0 for _, suite in results)
    sys.exit(1 if any_failed else 0)


# ── litmus parse ────────────────────────────────────────────────────


@main.command()
@click.argument("file")
def parse(file: str):
    """Parse a .metric (or YAML) file and display the structured output."""
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
        for null_rule in spec.trust.null_rules:
            console.print(
                f"    - null_rate({null_rule.column}): < {null_rule.max_percentage}%"
            )
        for volume_rule in spec.trust.volume_rules:
            table = f"({volume_rule.table})" if volume_rule.table else ""
            console.print(
                f"    - volume_change{table}"
                f"({volume_rule.period}): < {volume_rule.max_drop_percentage}%"
            )
        for range_rule in spec.trust.range_rules:
            console.print(
                f"    - value_range: [{range_rule.min_value}, {range_rule.max_value}]"
            )
        for change_rule in spec.trust.change_rules:
            console.print(
                f"    - value_change({change_rule.period}):"
                f" < {change_rule.max_change_percentage}%"
            )
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

_SUPPORTED_WAREHOUSES = ("duckdb", "sqlite", "postgres", "snowflake", "bigquery")

_EXAMPLE_METRIC = """\
Metric: Example Revenue
Description: Total revenue from completed orders, computed from the seeded demo data.
Owner: data-team
Tags: finance, example

Source: orders

Given all records from orders table
  And status is "completed"
  And amount is present

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

_GITIGNORE = """\
# Local credentials — never commit
.env

# Local history / cache
.litmus/

# Local demo DB files (regenerate via the project's seed script if needed)
*.duckdb
*.sqlite

# Generated reports
litmus-share/
report.html
report.json
"""

_ENV_EXAMPLES = {
    "duckdb": "# DuckDB runs locally — no credentials needed.\n",
    "sqlite": "# SQLite runs locally — no credentials needed.\n",
    "postgres": (
        "# Fill these in, then `source .env` before running litmus.\n"
        "export LITMUS_WAREHOUSE_USER=your_user\n"
        "export LITMUS_WAREHOUSE_PASSWORD=your_password\n"
    ),
    "snowflake": (
        "# Fill these in, then `source .env` before running litmus.\n"
        "export LITMUS_WAREHOUSE_USER=your_user\n"
        "export LITMUS_WAREHOUSE_PASSWORD=your_password\n"
    ),
    "bigquery": (
        "# BigQuery uses application-default credentials:\n"
        "#   gcloud auth application-default login\n"
        "# No user/password env vars needed.\n"
    ),
}


def _render_warehouse_block(warehouse: str, database: str) -> str:
    if warehouse in ("duckdb", "sqlite"):
        return (
            f"warehouse:\n"
            f"  type: {warehouse}\n"
            f'  database: "{database}"\n'
        )
    if warehouse == "postgres":
        return (
            "warehouse:\n"
            "  type: postgres\n"
            "  host: localhost\n"
            "  port: 5432\n"
            f"  database: {database}\n"
            "  schema: public\n"
            "  # Credentials come from LITMUS_WAREHOUSE_USER / LITMUS_WAREHOUSE_PASSWORD\n"
        )
    if warehouse == "snowflake":
        return (
            "warehouse:\n"
            "  type: snowflake\n"
            "  account: your_account\n"
            f"  database: {database}\n"
            "  schema: PUBLIC\n"
            "  warehouse: COMPUTE_WH\n"
            "  role: ANALYST\n"
            "  # Credentials come from LITMUS_WAREHOUSE_USER / LITMUS_WAREHOUSE_PASSWORD\n"
        )
    if warehouse == "bigquery":
        return (
            "warehouse:\n"
            "  type: bigquery\n"
            f"  database: {database}  # GCP project ID\n"
            "  schema: your_dataset\n"
            "  # Auth via: gcloud auth application-default login\n"
        )
    raise click.BadParameter(f"Unknown warehouse type: {warehouse}")


def _render_config(warehouse: str, database: str) -> str:
    return (
        "# litmus.yml\n"
        "version: 1\n"
        "\n"
        "# Where your .metric files live\n"
        "metrics_dir: metrics/\n"
        "\n"
        "# Warehouse connection\n"
        f"{_render_warehouse_block(warehouse, database)}"
        "\n"
        "# Check defaults (overridable per metric)\n"
        "defaults:\n"
        "  freshness: 24 hours\n"
        "  null_rate: 5%\n"
        "  volume_change: 25%\n"
        "\n"
        "# Output\n"
        "reporting:\n"
        "  format: console  # console | json | html | markdown\n"
        "  colors: true\n"
    )


def _render_readme(project_name: str, warehouse: str, database: str) -> str:
    run_line = "litmus check metrics/"
    seed_line = ""
    if warehouse in ("duckdb", "sqlite"):
        seed_line = (
            f"A demo `{database}` file was seeded with an `orders` table so "
            "`litmus check` works right away.\n\n"
        )
    else:
        seed_line = (
            f"Point `{database}` at a real `orders` table (or edit "
            "`metrics/example.metric` to match your schema) before running "
            "checks.\n\n"
        )

    return (
        f"# {project_name}\n\n"
        "A Litmus project — canonical metric contracts with built-in "
        "data trust checks.\n\n"
        "## Quickstart\n\n"
        f"{seed_line}"
        "```bash\n"
        f"{run_line}\n"
        "```\n\n"
        "## Layout\n\n"
        "- `litmus.yml` — warehouse connection + defaults\n"
        "- `metrics/` — one `.metric` file per metric\n"
        "- `.env.example` — template for credentials (copy to `.env`, "
        "then `source .env`)\n\n"
        "## Common commands\n\n"
        "```bash\n"
        "litmus check metrics/                  # run trust checks\n"
        "litmus explain metrics/example.metric  # plain-English doc\n"
        "litmus report metrics/ -f html -o report.html\n"
        "litmus share metrics/                  # self-contained dashboard\n"
        "```\n"
    )


def _seed_duckdb(db_path: Path) -> None:
    """Seed a small orders table so `litmus check` works on first run."""
    import duckdb

    conn = duckdb.connect(str(db_path))
    try:
        conn.execute(
            """
            CREATE TABLE orders (
                order_id    BIGINT PRIMARY KEY,
                customer_id BIGINT NOT NULL,
                status      VARCHAR NOT NULL,
                amount      DOUBLE,
                order_date  DATE NOT NULL,
                updated_at  TIMESTAMP
            )
            """
        )
        conn.execute(
            """
            INSERT INTO orders VALUES
              (1, 101, 'completed', 120.00, DATE '2026-04-10',
               CAST(CURRENT_TIMESTAMP AS TIMESTAMP)),
              (2, 102, 'completed', 450.50, DATE '2026-04-11',
               CAST(CURRENT_TIMESTAMP AS TIMESTAMP)),
              (3, 103, 'pending',   80.00,  DATE '2026-04-11',
               CAST(CURRENT_TIMESTAMP AS TIMESTAMP)),
              (4, 104, 'completed', 1200.00, DATE '2026-04-12',
               CAST(CURRENT_TIMESTAMP AS TIMESTAMP)),
              (5, 105, 'completed', 320.25, DATE '2026-04-13',
               CAST(CURRENT_TIMESTAMP AS TIMESTAMP)),
              (6, 106, 'completed', 75.99,  DATE '2026-04-14',
               CAST(CURRENT_TIMESTAMP AS TIMESTAMP)),
              (7, 107, 'completed', 890.00, DATE '2026-04-15',
               CAST(CURRENT_TIMESTAMP AS TIMESTAMP)),
              (8, 108, 'completed', 44.50,  DATE '2026-04-16',
               CAST(CURRENT_TIMESTAMP AS TIMESTAMP))
            """
        )
    finally:
        conn.close()


def _seed_sqlite(db_path: Path) -> None:
    import sqlite3

    conn = sqlite3.connect(str(db_path))
    try:
        conn.execute(
            """
            CREATE TABLE orders (
                order_id    INTEGER PRIMARY KEY,
                customer_id INTEGER NOT NULL,
                status      TEXT NOT NULL,
                amount      REAL,
                order_date  TEXT NOT NULL,
                updated_at  TEXT DEFAULT (datetime('now'))
            )
            """
        )
        conn.executemany(
            "INSERT INTO orders (order_id, customer_id, status, amount, order_date) "
            "VALUES (?, ?, ?, ?, ?)",
            [
                (1, 101, "completed", 120.00, "2026-04-10"),
                (2, 102, "completed", 450.50, "2026-04-11"),
                (3, 103, "pending", 80.00, "2026-04-11"),
                (4, 104, "completed", 1200.00, "2026-04-12"),
                (5, 105, "completed", 320.25, "2026-04-13"),
                (6, 106, "completed", 75.99, "2026-04-14"),
                (7, 107, "completed", 890.00, "2026-04-15"),
                (8, 108, "completed", 44.50, "2026-04-16"),
            ],
        )
        conn.commit()
    finally:
        conn.close()


def _default_database(warehouse: str, project_name: str) -> str:
    if warehouse == "duckdb":
        return "demo.duckdb"
    if warehouse == "sqlite":
        return "demo.sqlite"
    # For remote warehouses we have no basis to guess the real database name —
    # using the project slug tends to be wrong. Leave an obvious TODO so the
    # user is nudged to fill it in before running checks.
    return "TODO_your_database_name"


@main.command()
@click.argument("project_name", required=False)
@click.option(
    "--warehouse",
    type=click.Choice(_SUPPORTED_WAREHOUSES),
    default=None,
    help="Warehouse type. Prompts if omitted and stdin is a TTY; defaults to duckdb otherwise.",
)
@click.option(
    "--database",
    default=None,
    help="Database name (postgres/snowflake/bigquery) or file path (duckdb/sqlite).",
)
@click.option(
    "--yes", "-y", "skip_prompts", is_flag=True,
    help="Skip interactive prompts and use defaults.",
)
@click.option(
    "--force", is_flag=True,
    help="Overwrite existing files in the target directory.",
)
def init(
    project_name: str | None,
    warehouse: str | None,
    database: str | None,
    skip_prompts: bool,
    force: bool,
):
    """Initialize a new litmus project.

    \b
    Examples:
      litmus init                        # prompts for a project name (e.g. sales-metrics)
      litmus init sales-metrics          # create ./sales-metrics/ and scaffold into it
      litmus init . --yes                # scaffold into the current directory, no prompts
      litmus init sales-metrics --warehouse postgres --yes
    """
    # Prompt for missing values unless the caller explicitly opted out with --yes.
    # This mirrors `dbt init` — a bare `litmus init` should ask for a project name.
    interactive = not skip_prompts

    # Resolve project name → target directory.
    # Precedence: positional arg > interactive prompt > cwd (used under --yes).
    if project_name is None and interactive:
        project_name = click.prompt(
            "Project name (e.g. sales-metrics, or '.' for current dir)",
            default="my-metrics",
        )

    if project_name and project_name != ".":
        target = Path(project_name)
        if target.exists() and any(target.iterdir()) and not force:
            console.print(
                f"[red]Directory {target}/ already exists and is not empty. "
                "Re-run with --force to scaffold anyway.[/red]"
            )
            sys.exit(1)
        target.mkdir(parents=True, exist_ok=True)
        display_name = project_name
    else:
        target = Path(".")
        display_name = Path.cwd().name or "litmus-project"

    # Resolve warehouse type. Prompt only if interactive and no flag given.
    if warehouse is None:
        if interactive:
            warehouse = click.prompt(
                "Warehouse type",
                type=click.Choice(_SUPPORTED_WAREHOUSES),
                default="duckdb",
            )
        else:
            warehouse = "duckdb"

    # Resolve database name/path.
    default_db = _default_database(warehouse, display_name)
    if database is None:
        if interactive:
            hint = " (file path)" if warehouse in ("duckdb", "sqlite") else ""
            database = click.prompt(
                f"Database{hint}",
                default=default_db,
            )
        else:
            database = default_db

    assert warehouse is not None and database is not None

    # Write project files.
    created: list[str] = []

    def _write(relpath: str, content: str, label: str) -> None:
        path = target / relpath
        if path.exists() and not force:
            console.print(f"[yellow]{relpath} already exists, skipping.[/yellow]")
            return
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content)
        created.append(f"{relpath:32s} — {label}")

    _write("litmus.yml", _render_config(warehouse, database), "warehouse config")
    (target / "metrics").mkdir(exist_ok=True)
    _write("metrics/example.metric", _EXAMPLE_METRIC, "starter metric")
    _write(".env.example", _ENV_EXAMPLES[warehouse], "credential template")
    _write(".gitignore", _GITIGNORE, "ignore rules")
    _write("README.md", _render_readme(display_name, warehouse, database), "project readme")

    # Seed a demo DB for local warehouses so first `check` works.
    if warehouse == "duckdb":
        db_file = target / database
        if db_file.exists() and not force:
            console.print(f"[yellow]{database} already exists, skipping seed.[/yellow]")
        else:
            if db_file.exists():
                db_file.unlink()
            _seed_duckdb(db_file)
            created.append(f"{database:32s} — seeded demo data (8 orders)")
    elif warehouse == "sqlite":
        db_file = target / database
        if db_file.exists() and not force:
            console.print(f"[yellow]{database} already exists, skipping seed.[/yellow]")
        else:
            if db_file.exists():
                db_file.unlink()
            _seed_sqlite(db_file)
            created.append(f"{database:32s} — seeded demo data (8 orders)")

    console.print()
    if created:
        console.print("[bold green]Created:[/bold green]")
        for item in created:
            console.print(f"  {item}")
    console.print()
    if warehouse in ("duckdb", "sqlite"):
        if project_name and project_name != ".":
            console.print(
                f"[bold]Next:[/bold]  cd {project_name} && litmus check metrics/"
            )
        else:
            console.print("[bold]Next:[/bold]  litmus check metrics/")
    else:
        prefix = f"cd {project_name} && " if project_name and project_name != "." else ""
        console.print("[bold]Next steps:[/bold]")
        console.print(f"  1. {prefix}cp .env.example .env")
        console.print("  2. Fill in credentials in .env and the connection in litmus.yml")
        console.print("  3. source .env && litmus check metrics/")
    console.print()


# ── litmus import-dbt ───────────────────────────────────────────────


@main.command("import-dbt")
@click.argument("manifest_path")
@click.option(
    "--output-dir", "-o", default="metrics",
    help="Directory for generated .metric files.",
)
@click.option(
    "--push",
    "push_flag",
    is_flag=True,
    default=False,
    help=(
        "After writing .metric files, also push each metric's lineage graph"
        " (extracted from the manifest's parent_map, 3 hops deep) to a"
        " running Litmus server."
    ),
)
@click.option(
    "--endpoint",
    default=None,
    help="Litmus server URL for --push. Falls back to $LITMUS_ENDPOINT.",
)
@click.option(
    "--api-key",
    "api_key",
    default=None,
    help="API key for --push. Falls back to $LITMUS_API_KEY.",
)
def import_dbt(
    manifest_path: str,
    output_dir: str,
    push_flag: bool,
    endpoint: str | None,
    api_key: str | None,
):
    """Import metric definitions from a dbt manifest.json.

    With --push, also upserts each metric and its lineage (up to 3 hops
    upstream through the dbt parent_map) into a running Litmus catalog
    server. The two-step flow (write files, then push) keeps the local
    artifacts authoritative — the server is a mirror, never the source.
    """
    import json as _json

    from litmus.generators.dbt_importer import (
        build_lineage,
        generate_metric_file,
        import_dbt_manifest,
    )

    manifest_path_obj = Path(manifest_path)
    if not manifest_path_obj.exists():
        console.print(f"[red]File not found: {manifest_path}[/red]")
        sys.exit(1)

    try:
        specs = import_dbt_manifest(manifest_path_obj)
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

    # Track file paths per spec name so --push can read them back for the
    # upsert — we want the original .metric text, not a round-tripped
    # generate_metric_file output.
    paths_by_name: dict[str, Path] = {}
    for spec in specs:
        filename = spec.name.lower().replace(" ", "_") + ".metric"
        file_path = out_dir / filename
        file_path.write_text(generate_metric_file(spec))
        paths_by_name[spec.name] = file_path
        console.print(f"  {file_path}")

    console.print()
    console.print("Review and edit each file to add Trust rules and plain-English descriptions.")
    console.print()

    if not push_flag:
        return

    # --push flow: upsert every metric, then POST its lineage subgraph.
    from litmus.api_push import PushConfig, PushError, push_lineage, push_results

    push_cfg = PushConfig.from_env(endpoint=endpoint, api_key=api_key)
    if push_cfg is None:
        console.print(
            "[red]--push requires --endpoint or $LITMUS_ENDPOINT.[/red]"
        )
        sys.exit(1)

    # Load the manifest once, reuse across metrics.
    with open(manifest_path_obj) as f:
        manifest = _json.load(f)

    # Re-parse the freshly written .metric files so upsert sees parseable text.
    from litmus.checks.runner import CheckSuite
    from litmus.parser import parse_metric_file
    from litmus.spec.metric_spec import MetricSpec

    reparsed: list[tuple[MetricSpec, CheckSuite]] = []
    spec_texts: dict[str, str] = {}
    for spec in specs:
        file_path = paths_by_name[spec.name]
        spec_text = file_path.read_text(encoding="utf-8")
        try:
            reparsed_spec = parse_metric_file(file_path)
        except Exception as exc:
            console.print(
                f"[yellow]Skipping push for {spec.name}: "
                f"generated .metric failed to re-parse ({exc})[/yellow]"
            )
            continue
        spec_texts[reparsed_spec.name] = spec_text
        reparsed.append((reparsed_spec, CheckSuite(metric_name=reparsed_spec.name)))

    if not reparsed:
        console.print("[yellow]Nothing to push.[/yellow]")
        return

    try:
        metric_ids = push_results(push_cfg, reparsed, spec_texts=spec_texts)
    except PushError as exc:
        console.print(f"[red]Push failed: {exc}[/red]")
        sys.exit(1)

    # Now push lineage for each metric. We need the *dbt* short name to walk
    # the parent_map — the Litmus display name (e.g. "Total Revenue") won't
    # match. We recover it from the original manifest lookup.
    dbt_names_by_spec_name: dict[str, str] = {}
    for uid, data in (manifest.get("metrics") or {}).items():
        display = (data.get("label") or data.get("name") or "").replace("_", " ").title()
        dbt_names_by_spec_name[display] = data.get("name") or uid.split(".")[-1]
    for uid, node in (manifest.get("nodes") or {}).items():
        if node.get("resource_type") != "model":
            continue
        short = node.get("name", "")
        display = short.replace("_", " ").title()
        dbt_names_by_spec_name.setdefault(display, short)

    pushed = 0
    for (spec_obj, _), metric_id in zip(reparsed, metric_ids):
        dbt_name = dbt_names_by_spec_name.get(spec_obj.name)
        if dbt_name is None:
            continue
        lineage = build_lineage(manifest, dbt_name)
        if not lineage.nodes:
            continue
        nodes_payload = [
            {"id": n.id, "label": n.label, "kind": n.kind}
            for n in lineage.nodes
        ]
        edges_payload = [
            {"from": e.from_id, "to": e.to_id} for e in lineage.edges
        ]
        try:
            push_lineage(push_cfg, metric_id, nodes_payload, edges_payload)
            pushed += 1
        except PushError as exc:
            console.print(
                f"[yellow]Lineage push failed for {spec_obj.name}: {exc}[/yellow]"
            )

    console.print(
        f"[dim]Pushed {len(metric_ids)} metric(s) and "
        f"{pushed} lineage graph(s) to {push_cfg.endpoint}[/dim]"
    )


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


# ── litmus explain-run ──────────────────────────────────────────────


@main.command("explain-run")
@click.argument("run_id")
@click.option(
    "--endpoint",
    default=None,
    help=(
        "Litmus server URL. Falls back to $LITMUS_ENDPOINT. Required — the "
        "AI explainer lives on the server, not in the CLI."
    ),
)
@click.option(
    "--api-key",
    "api_key",
    default=None,
    help="API key for the Litmus server. Falls back to $LITMUS_API_KEY.",
)
@click.option(
    "--regenerate",
    is_flag=True,
    default=False,
    help="Force regeneration even if an explanation is already cached.",
)
def explain_run(
    run_id: str,
    endpoint: str | None,
    api_key: str | None,
    regenerate: bool,
):
    """Ask a Litmus server to explain a failed/errored run with AI.

    The CLI does **not** talk to Anthropic directly — it proxies through the
    server so the API key, history, and privacy disclosure all live in one
    place. See ``docs/ai-explanations.md`` for what gets sent.
    """
    import json as _json
    import os
    import urllib.error
    import urllib.request

    from rich.panel import Panel

    ep = (endpoint or os.environ.get("LITMUS_ENDPOINT") or "").rstrip("/")
    if not ep:
        console.print(
            "[red]No endpoint given. Pass --endpoint or set "
            "$LITMUS_ENDPOINT.[/red]"
        )
        sys.exit(1)

    key = api_key or os.environ.get("LITMUS_API_KEY")
    headers = {"Content-Type": "application/json"}
    if key:
        headers["Authorization"] = f"Bearer {key}"

    url = f"{ep}/api/v1/runs/{run_id}/explain"
    if regenerate:
        url += "?regenerate=true"

    req = urllib.request.Request(
        url, data=b"{}", method="POST", headers=headers
    )
    try:
        # 45s client-side timeout — the server promises 30s, leaves 15s slack.
        with urllib.request.urlopen(req, timeout=45) as resp:
            body = _json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")
        console.print(f"[red]HTTP {exc.code}: {detail}[/red]")
        sys.exit(1)
    except urllib.error.URLError as exc:
        console.print(f"[red]Could not reach {ep}: {exc.reason}[/red]")
        sys.exit(1)

    console.print(
        Panel.fit(
            body.get("hypothesis", "(no hypothesis)"),
            title=f"Why did run {run_id} fail?",
            border_style="yellow",
        )
    )
    console.print(
        Panel.fit(
            body.get("suggested_action", "(no suggested action)"),
            title="Suggested next step",
            border_style="cyan",
        )
    )
    console.print(
        f"[dim]model={body.get('model_id', '?')}  "
        f"generated={body.get('created_at', '?')}[/dim]"
    )


# ── litmus reconcile ────────────────────────────────────────────────


@main.command("reconcile")
@click.argument("metric_slug")
@click.option(
    "--endpoint",
    default=None,
    help=(
        "Litmus server URL. Falls back to $LITMUS_ENDPOINT. Required — "
        "reconciliation lives on the server, not in the CLI."
    ),
)
@click.option(
    "--api-key",
    "api_key",
    default=None,
    help="API key for the Litmus server. Falls back to $LITMUS_API_KEY.",
)
def reconcile(
    metric_slug: str,
    endpoint: str | None,
    api_key: str | None,
):
    """Trigger BI reconciliation for a metric on a Litmus server.

    POSTs to ``/api/v1/metrics/{slug}/reconcile``. The server iterates the
    metric's BI mappings, fetches each value, computes the delta vs the
    latest warehouse run, and returns one row per source.
    """
    import json as _json
    import os
    import urllib.error
    import urllib.request

    from rich.table import Table

    ep = (endpoint or os.environ.get("LITMUS_ENDPOINT") or "").rstrip("/")
    if not ep:
        console.print(
            "[red]No endpoint given. Pass --endpoint or set "
            "$LITMUS_ENDPOINT.[/red]"
        )
        sys.exit(1)

    key = api_key or os.environ.get("LITMUS_API_KEY")
    headers = {"Content-Type": "application/json"}
    if key:
        headers["Authorization"] = f"Bearer {key}"

    url = f"{ep}/api/v1/metrics/{metric_slug}/reconcile"
    req = urllib.request.Request(url, data=b"{}", method="POST", headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=60) as resp:
            rows = _json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")
        console.print(f"[red]HTTP {exc.code}: {detail}[/red]")
        sys.exit(1)
    except urllib.error.URLError as exc:
        console.print(f"[red]Could not reach {ep}: {exc.reason}[/red]")
        sys.exit(1)

    if not rows:
        console.print(
            f"[yellow]No BI mappings registered for {metric_slug!r}.[/yellow] "
            "Add one via POST /api/v1/metrics/{id}/bi-mappings first."
        )
        return

    table = Table(title=f"Reconciliation — {metric_slug}")
    table.add_column("Source")
    table.add_column("Value", justify="right")
    table.add_column("Delta", justify="right")
    table.add_column("Status")
    table.add_column("Notes")
    for row in rows:
        status_raw = (row.get("status") or "").lower()
        status_color = {
            "pass": "green",
            "warn": "yellow",
            "fail": "red",
        }.get(status_raw, "white")
        delta = row.get("delta", 0.0) or 0.0
        value = row.get("value", 0.0) or 0.0
        notes = row.get("error") or row.get("identifier") or ""
        table.add_row(
            str(row.get("source", "?")),
            f"{value:,.2f}",
            f"{delta * 100:+.2f}%",
            f"[{status_color}]{status_raw.upper() or '?'}[/{status_color}]",
            str(notes),
        )
    console.print(table)


if __name__ == "__main__":
    main()
