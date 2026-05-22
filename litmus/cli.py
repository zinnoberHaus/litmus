"""CLI entry point — Litmus, your AI data agents team."""

from __future__ import annotations

import sys
from pathlib import Path

import click
from rich.console import Console

from litmus import __version__

console = Console()


def _warehouse_url() -> str:
    """Resolve the warehouse URL: env var → project state → local DuckDB."""
    import json
    import os

    env = os.environ.get("LITMUS_WAREHOUSE_URL")
    if env:
        return env
    state = Path(".litmus/state.json")
    if state.exists():
        try:
            url = json.loads(state.read_text()).get("warehouse_url")
            if url:
                return str(url)
        except (json.JSONDecodeError, OSError):
            pass
    return "duckdb:///./data/warehouse.duckdb"


@click.group(invoke_without_command=True)
@click.version_option(version=__version__, prog_name="litmus")
@click.pass_context
def main(ctx: click.Context) -> None:
    """Litmus — your AI data agents team.

    Install, run `litmus init`, and you get a data team plus the project around
    your data: ingestion, transforms, dashboards, tests. Then work with the team.

    \b
    Two ways to use the team:
      litmus                 talk to the team (interactive console)
      litmus agent "<task>"  dispatch a one-off task to the team

    \b
    Project commands (dbt-style, fronted by the agents):
      litmus init        set up a project (the wizard)
      litmus configure   change the AI model or data sources
      litmus run         ingest -> transform
      litmus test        run your data tests
      litmus dashboard   build / open a visualization
      litmus add <csv>   register a CSV source in one shot
      litmus ingest      run an ingest pipeline
      litmus transform   run a transform
      litmus connect     wire up Notion / Linear / Anthropic / Slack
      litmus doctor      diagnose setup

    Running `litmus` with no subcommand drops into the interactive agent console.
    """
    if ctx.invoked_subcommand is None:
        from litmus.tui import is_tty, run_tui

        if is_tty():
            run_tui()
        else:
            click.echo(ctx.get_help())


# ── litmus init ─────────────────────────────────────────────────────


@main.command()
@click.argument("project_name", required=False)
@click.option(
    "--model", "model_id", default=None,
    help="AI model id (claude-opus, claude-sonnet, claude-haiku, gpt-5, "
         "gemini-pro, local). Prompts if omitted.",
)
@click.option(
    "--source", "source_ids", multiple=True,
    help="Data source id (repeatable): sample, warehouse, postgres, snowflake, "
         "bigquery, csv, rest, stripe, sheets. Prompts if omitted.",
)
@click.option(
    "--yes", "-y", "skip_prompts", is_flag=True,
    help="Skip prompts; use defaults (Claude Sonnet + sample/duckdb).",
)
@click.option(
    "--force", is_flag=True,
    help="Overwrite existing files in the target directory.",
)
def init(
    project_name: str | None,
    model_id: str | None,
    source_ids: tuple[str, ...],
    skip_prompts: bool,
    force: bool,
):
    """Set up your AI data agents team — the guided init wizard.

    \b
    project name → pick an AI model → choose data inflow → build the project.

    \b
    Examples:
      litmus init                         # interactive wizard in the current dir
      litmus init my-project              # create ./my-project/ and set up there
      litmus init . --yes                 # non-interactive, sensible defaults
      litmus init . --model claude-opus --source sample --source postgres --yes
    """
    from litmus.wizard import run_wizard

    # Resolve project name → target directory.
    # Precedence: positional arg > cwd. A named subdir must be empty (or --force).
    if project_name and project_name != ".":
        target = Path(project_name)
        if target.exists() and any(target.iterdir()) and not force:
            console.print(
                f"[red]Directory {target}/ already exists and is not empty. "
                "Re-run with --force to set up anyway.[/red]"
            )
            sys.exit(1)
        target.mkdir(parents=True, exist_ok=True)
        wizard_name: str | None = project_name
    else:
        target = Path(".")
        # Interactive cwd init lets the wizard prompt for the name (defaulting to
        # the cwd name); under --yes we use the cwd name directly.
        wizard_name = (Path.cwd().name or "litmus-project") if skip_prompts else None

    run_wizard(
        target,
        skip_prompts=skip_prompts,
        project_name=wizard_name,
        model_id=model_id,
        source_ids=list(source_ids) or None,
        force=force,
    )


# ── litmus configure ────────────────────────────────────────────────


@main.command()
def configure() -> None:
    """Reconfigure the project — change the AI model or data sources."""
    from litmus.wizard import reconfigure

    reconfigure(Path("."))


# ── data commands: ingest / add / transform / run ───────────────────
# (Heavy imports stay inside each command so `litmus --help` stays fast.)


@main.command()
@click.argument("pipeline_name", required=False)
def ingest(pipeline_name: str | None) -> None:
    """Run an ingest pipeline (or list available pipelines)."""
    from litmus.pipelines.runner import list_pipelines, run_ingest

    if not pipeline_name:
        for p in list_pipelines():
            click.echo(f"  {p.stem}")
        return

    run_ingest(pipeline_name)


@main.command()
@click.argument("source", type=click.Path(exists=True, dir_okay=False, readable=True))
@click.option(
    "--name", "-n",
    default=None,
    help="Source name. Defaults to the file stem (e.g. 'customers' for customers.csv).",
)
@click.option(
    "--mode",
    type=click.Choice(["replace", "append"]),
    default="replace",
    show_default=True,
    help="Ingest mode for re-runs.",
)
def add(source: str, name: str | None, mode: str) -> None:
    """Register a new data source from a file path. One-shot: copy → spec → ingest.

    \b
    Examples:
      litmus add ~/Downloads/customers.csv
      litmus add ./stripe-charges.csv --name stripe_charges
      litmus add /tmp/events.csv --mode append
    """
    import shutil as _shutil
    from pathlib import Path as _Path

    import yaml

    src = _Path(source).expanduser().resolve()
    if src.suffix.lower() != ".csv":
        click.echo(
            f"Only .csv is supported right now (got {src.suffix or '<no extension>'}). "
            "Postgres / Stripe / REST are on the roadmap."
        )
        sys.exit(1)

    stem = name or src.stem.replace("-", "_").replace(" ", "_").lower()
    table = f"raw_{stem}"

    # 1. Copy CSV into the project's data/raw/ (idempotent).
    raw_dir = _Path("data/raw")
    raw_dir.mkdir(parents=True, exist_ok=True)
    dest_csv = raw_dir / src.name
    if dest_csv.resolve() != src:
        _shutil.copy(src, dest_csv)
    click.echo(f"  ✓ copied {src.name} → data/raw/")

    # 2. Generate the ingest spec.
    pipelines_dir = _Path("pipelines")
    pipelines_dir.mkdir(exist_ok=True)
    spec_path = pipelines_dir / f"{stem}.yaml"
    spec = {
        "source": {"type": "csv", "path": f"./data/raw/{src.name}"},
        "target": {"table": table, "mode": mode},
        "schedule": "manual",
    }
    spec_path.write_text(yaml.safe_dump(spec, sort_keys=False))
    click.echo(f"  ✓ wrote {spec_path}")

    # 3. Run the first ingest.
    from litmus.pipelines.runner import run_ingest

    run_ingest(stem)

    click.echo("")
    click.echo("Source registered. Next steps:")
    sample_q = f"SELECT * FROM {table} LIMIT 5"
    click.echo(f"  • Query it:        duckdb data/warehouse.duckdb -c '{sample_q}'")
    click.echo(f"  • Transform it:    litmus agent \"build a transform on {table}\"")
    click.echo(f"  • Re-run:          litmus ingest {stem}")


@main.command()
@click.argument("transform_name", required=False)
def transform(transform_name: str | None) -> None:
    """Run a SQL transform (or list available transforms)."""
    from litmus.pipelines.runner import list_transforms, run_transform

    if not transform_name:
        for t in list_transforms():
            click.echo(f"  {t.stem}")
        return

    run_transform(transform_name)


@main.command()
def run() -> None:
    """Run everything: every ingest pipeline, then every transform."""
    from litmus.pipelines.runner import run_all

    run_all()


# ── litmus test ─────────────────────────────────────────────────────


@main.command()
def test() -> None:
    """Run your data tests — each tests/*.sql must return zero rows to pass."""
    tests_dir = Path("tests")
    test_files = sorted(tests_dir.glob("*.sql")) if tests_dir.exists() else []
    if not test_files:
        click.echo('No tests in tests/. Ask the team: litmus agent "add a test that ..."')
        return

    warehouse_url = _warehouse_url()
    if not warehouse_url.startswith("duckdb://"):
        click.echo(f"Only DuckDB test execution is wired right now ({warehouse_url}).")
        click.echo("Run your tests against the warehouse directly, or ask the team.")
        sys.exit(1)

    import duckdb

    db_path = warehouse_url.replace("duckdb:///", "").replace("duckdb://", "")
    failures = 0
    for tf in test_files:
        try:
            con = duckdb.connect(db_path, read_only=True)
            rows = con.execute(tf.read_text()).fetchall()
            con.close()
            if rows:
                failures += 1
                click.echo(f"  ✗ {tf.stem} — {len(rows)} problem row(s)")
            else:
                click.echo(f"  ✓ {tf.stem}")
        except Exception as exc:  # noqa: BLE001
            failures += 1
            click.echo(f"  ✗ {tf.stem} — error: {exc}")

    click.echo("")
    if failures:
        click.echo(f"{failures} test(s) failed.")
        sys.exit(1)
    click.echo(f"All {len(test_files)} test(s) passed.")


# ── litmus dashboard ────────────────────────────────────────────────


@main.command()
@click.option("--port", default=8501, show_default=True)
def dashboard(port: int) -> None:
    """Start the Streamlit dashboard server."""
    import subprocess

    dashboards_dir = Path("dashboards")
    if not dashboards_dir.exists() or not any(dashboards_dir.glob("*.py")):
        click.echo("No dashboards found in dashboards/.")
        click.echo('Ask the team: litmus agent "build a dashboard for ..."')
        sys.exit(1)

    home = dashboards_dir / "home.py"
    overview = dashboards_dir / "overview.py"
    target = home if home.exists() else (overview if overview.exists()
                                         else next(dashboards_dir.glob("*.py")))

    click.echo(f"Starting Streamlit at http://localhost:{port}/  (serving {target})")
    subprocess.run(["streamlit", "run", str(target), "--server.port", str(port)])


# ── litmus demo ─────────────────────────────────────────────────────


@main.command()
def demo() -> None:
    """Load the bundled sample dataset into a local DuckDB warehouse."""
    from litmus.wizard import _load_sample

    _load_sample(Path("."))
    click.echo("Sample loaded into data/warehouse.duckdb. Try: litmus dashboard")


# ── litmus doctor ───────────────────────────────────────────────────


@main.command()
def doctor() -> None:
    """Diagnose setup — warehouse reachable, MCP servers configured, secrets present."""
    from litmus.diagnostics import run_doctor

    ok = run_doctor()
    sys.exit(0 if ok else 1)


# ── litmus connect ──────────────────────────────────────────────────


@main.command()
@click.argument(
    "service",
    type=click.Choice(
        ["notion", "linear", "anthropic", "slack"], case_sensitive=False
    ),
)
def connect(service: str) -> None:
    """Wire up an integration after init. Prompts for the key, writes .env.

    \b
    Examples:
      litmus connect notion
      litmus connect linear
      litmus connect anthropic
      litmus connect slack
    """
    from litmus.tui import _write_env_file

    service = service.lower()
    spec = {
        "notion": {
            "env_var": "NOTION_API_KEY",
            "url": "https://notion.so/profile/integrations",
            "label": "Notion API key",
        },
        "linear": {
            "env_var": "LINEAR_API_KEY",
            "url": "https://linear.app/settings/api",
            "label": "Linear API key",
        },
        "anthropic": {
            "env_var": "LITMUS_ANTHROPIC_API_KEY",
            "url": "https://console.anthropic.com/settings/keys",
            "label": "Anthropic API key",
        },
        "slack": {
            "env_var": "LITMUS_SLACK_WEBHOOK_URL",
            "url": "https://api.slack.com/messaging/webhooks",
            "label": "Slack incoming webhook URL",
        },
    }[service]

    click.echo(f"Get a {service.title()} key here: {spec['url']}")
    value = click.prompt(spec["label"], default="", show_default=False, hide_input=True).strip()
    if not value:
        click.echo("(nothing entered — aborted)")
        return

    _write_env_file({spec["env_var"]: value})
    click.echo(f"✓ wrote {spec['env_var']} to .env (chmod 600).")


# ── litmus ask / agent ──────────────────────────────────────────────


def _dispatch_to_team(text: str, *, preamble: str = "") -> int:
    """Send a prompt to the agent team via the Claude Code CLI. Returns exit code."""
    import shutil
    import subprocess

    from litmus.runtime import claude_model_args, runtime_note
    from litmus.tui import DATA_ENGINEERING_SCOPE

    if not shutil.which("claude"):
        click.echo(
            "Claude Code is not installed. Get it at https://claude.ai/code "
            "(free), then re-run."
        )
        return 1

    note = runtime_note()
    if note:
        click.echo(note)

    # Ground the team in the project context the wizard wrote, if present.
    scope = DATA_ENGINEERING_SCOPE
    ctx = Path(".litmus/context.md")
    if ctx.exists():
        scope = scope + "\n\nProject context:\n" + ctx.read_text()

    full = f"{preamble}{text}" if preamble else text
    cmd = ["claude", "--print", full, "--append-system-prompt", scope]
    cmd += claude_model_args()
    cmd.append("--allow-dangerously-skip-permissions")
    result = subprocess.run(cmd)
    return result.returncode


@main.command()
@click.argument("prompt", nargs=-1, required=True)
def ask(prompt: tuple[str, ...]) -> None:
    """Ask the agent team a question. Stays in your terminal.

    \b
    Examples:
      litmus ask "@analyst what is our top customer by revenue?"
      litmus ask "@pipeline-builder build a daily revenue rollup"
    """
    sys.exit(_dispatch_to_team(" ".join(prompt)))


@main.command()
@click.argument("task", nargs=-1, required=True)
def agent(task: tuple[str, ...]) -> None:
    """Dispatch a one-off task to your data team.

    \b
    Examples:
      litmus agent "ingest the customers.csv and build a daily signups table"
      litmus agent "add a test that flags negative amounts"
      litmus agent "build a dashboard of revenue by market"
    """
    preamble = (
        "You are this project's AI data team. Carry out the following task "
        "end to end — verify the relevant source, transform it, and operate on "
        "the result. Use the sources/, transforms/, dashboards/, and tests/ "
        "folders. Task:\n\n"
    )
    sys.exit(_dispatch_to_team(" ".join(task), preamble=preamble))


if __name__ == "__main__":
    main()
