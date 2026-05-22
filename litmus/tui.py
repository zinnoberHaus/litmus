"""Interactive REPL launched by ``litmus`` with no subcommand.

Two phases:

1. **Bootstrap** — first time in a directory, walk the user through a
   minimal claude-style setup wizard (project name, sample data,
   warehouse, dbt detection, orchestrator, optional API keys).
2. **Agent mode** — after setup, drop straight into a chat REPL. Free
   text goes to the agent team via ``claude --print``. Slash commands
   handle deterministic local actions (/assets, /health, /dashboards,
   /chart, /menu, /help, /exit).

The TUI itself does not embed an LLM. Agent calls shell out to
Claude Code; that's where the model + tools live.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

import click
import yaml
from rich.console import Console
from rich.panel import Panel
from rich.table import Table

from litmus import __version__

STATE_DIR = Path(".litmus")
STATE_FILE = STATE_DIR / "state.json"

# Opt-in for the inline agent flow to bypass per-tool permission prompts.
# Off by default — the user picks it on first agent invocation.
SKIP_PERMS_ENV = "LITMUS_SKIP_AGENT_PERMS"

# Hard scope guardrail. Prepended to every `claude --print` invocation via
# --append-system-prompt so even free-text questions through the REPL stay
# in the data engineering lane. The per-agent .md files repeat this for the
# subagent layer; this is the belt-and-braces at the TUI boundary.
DATA_ENGINEERING_SCOPE = """
You are operating inside a Litmus project (an open-source AI data engineering
tool). Your scope is exclusively **modern data engineering**:
  - data ingestion (CSV / Postgres / Snowflake / BigQuery / Stripe / etc.)
  - SQL transforms and warehouse modeling (raw → mart, star schemas)
  - data quality contracts (.metric files, freshness / nulls / volume / range)
  - semantic models (semantic/*.yaml — entities, dimensions, measures, joins)
  - dashboards (Streamlit, reading from mart_* tables only)
  - dbt integration and orchestration (Airflow / Dagster / Prefect)

If the user asks about anything outside this scope — frontend development,
mobile apps, ML model training, DevOps infrastructure, general programming
help, life advice, jokes — give exactly this reply and stop:

  "I'm Litmus — I only do data engineering (ingest, SQL, warehouses, trust
   checks, dashboards). For that question, you'll want a different tool."

Don't try to help anyway. Don't add caveats. The redirect IS the answer.

Always ground your responses in this project's files:
  - .litmus/state.json       (warehouse type + URL + dbt + orchestrator)
  - semantic/*.yaml          (entity definitions — the source of truth for
                              what "revenue", "customer", etc. mean)
  - pipelines/*.yaml         (registered data sources)
  - transforms/*.sql         (mart table definitions)
  - metrics/*.metric         (trust contracts)
  - dashboards/*.py          (Streamlit pages)

Read these before answering. If a measure or table isn't defined, ask the
user before inventing one.
""".strip()

console = Console()


# ──────────────────────────────────────────────────────────────────────────
# Scaffolding helpers
# ──────────────────────────────────────────────────────────────────────────


def _install_agent_scaffold(cwd: Path) -> dict:
    """Copy the agent team (``.claude/`` + ``.mcp.json`` + ``AGENTS.md``) from
    the bundled templates into the user's project. Idempotent.

    Thin wrapper around :func:`litmus.scaffold.install_agent_team` so the TUI
    and ``litmus init`` share one scaffold implementation.
    """
    from litmus.scaffold import install_agent_team

    return install_agent_team(cwd)


def _detect_dbt_project(start: Path | None = None) -> Path | None:
    """Walk up from ``start`` looking for ``dbt_project.yml``."""
    cur = (start or Path.cwd()).resolve()
    for parent in (cur, *cur.parents):
        if (parent / "dbt_project.yml").is_file():
            return parent
    return None


def _load_state() -> dict:
    if STATE_FILE.exists():
        loaded: dict = json.loads(STATE_FILE.read_text())
        return loaded
    return {}


def _save_state(state: dict) -> None:
    STATE_DIR.mkdir(exist_ok=True)
    STATE_FILE.write_text(json.dumps(state, indent=2))


def _load_dotenv(env_path: Path | None = None) -> None:
    """Read ./.env and populate os.environ. Hand-rolled — no python-dotenv dep.

    Only sets variables that aren't already in the environment (so explicit
    `export FOO=...` in the user's shell wins over the file).
    """
    env_path = env_path or Path(".env")
    if not env_path.exists():
        return
    try:
        for line in env_path.read_text().splitlines():
            stripped = line.strip()
            if not stripped or stripped.startswith("#") or "=" not in stripped:
                continue
            k, _, v = stripped.partition("=")
            key = k.strip()
            value = v.strip().strip('"').strip("'")
            if key and key not in os.environ:
                os.environ[key] = value
    except OSError:
        # Unreadable .env shouldn't crash the TUI.
        pass


def _has_claude_code_auth() -> bool:
    """Best-effort check: does the user appear to have Claude Code logged in?

    We can't introspect Claude Code's auth directly, but the CLI creates
    ``~/.claude/`` on first login. If both the binary and that dir exist,
    odds are good they're authenticated.
    """
    if not shutil.which("claude"):
        return False
    claude_home = Path.home() / ".claude"
    return claude_home.exists()


def _llm_auth_state() -> dict:
    """Return current LLM auth situation: which method works (if any)."""
    api_key = os.environ.get("ANTHROPIC_API_KEY") or os.environ.get(
        "LITMUS_ANTHROPIC_API_KEY"
    )
    return {
        "has_api_key": bool(api_key),
        "has_claude_oauth": _has_claude_code_auth(),
        "ready": bool(api_key) or _has_claude_code_auth(),
    }


def _project_status() -> dict:
    """Snapshot of the current directory."""
    cwd = Path.cwd()
    return {
        "initialized": STATE_FILE.exists(),
        "has_warehouse": (cwd / "data" / "warehouse.duckdb").exists(),
        "pipelines": sorted(p.name for p in (cwd / "pipelines").glob("*.yaml"))
        if (cwd / "pipelines").exists() else [],
        "transforms": sorted(t.name for t in (cwd / "transforms").glob("*.sql"))
        if (cwd / "transforms").exists() else [],
        "metrics": sorted(m.name for m in (cwd / "metrics").glob("*.metric"))
        if (cwd / "metrics").exists() else [],
        "dashboards": sorted(d.name for d in (cwd / "dashboards").glob("*.py"))
        if (cwd / "dashboards").exists() else [],
        "semantic": sorted(s.name for s in (cwd / "semantic").glob("*.yaml"))
        if (cwd / "semantic").exists() else [],
        "notion_key": bool(os.environ.get("NOTION_API_KEY")),
        "linear_key": bool(os.environ.get("LINEAR_API_KEY")),
        "anthropic_key": bool(
            os.environ.get("LITMUS_ANTHROPIC_API_KEY")
            or os.environ.get("ANTHROPIC_API_KEY")
        ),
        "claude_cli": shutil.which("claude") is not None,
        "dbt_project": _detect_dbt_project(),
        "llm_auth": _llm_auth_state(),
    }


def _print_banner() -> None:
    console.print(
        Panel.fit(
            f"[bold cyan]Litmus[/bold cyan] [dim]v{__version__}[/dim] — "
            "agent-driven data engineering",
            border_style="cyan",
        )
    )


def _print_project_summary(status: dict) -> None:
    table = Table(show_header=False, box=None, padding=(0, 2))
    table.add_column("key", style="dim")
    table.add_column("value")

    table.add_row(
        "Project",
        "[green]initialized[/green]" if status["initialized"]
        else "[yellow]not initialized — setup runs next[/yellow]",
    )
    table.add_row(
        "Warehouse",
        "data/warehouse.duckdb" if status["has_warehouse"] else "[dim]none yet[/dim]",
    )
    table.add_row(
        "Tables",
        f"{len(status['pipelines'])} ingest, "
        f"{len(status['transforms'])} transforms, "
        f"{len(status['metrics'])} trust contracts, "
        f"{len(status['dashboards'])} dashboards, "
        f"{len(status['semantic'])} semantic entities",
    )

    def _badge(label: str, ok: bool, hint: str = "") -> str:
        if ok:
            return f"[green]✓[/green] {label}"
        return f"[red]✗[/red] {label} [dim]({hint})[/dim]"

    llm = status.get("llm_auth", {})
    if llm.get("has_api_key"):
        llm_label = "[green]✓[/green] LLM [dim](API key)[/dim]"
    elif llm.get("has_claude_oauth"):
        llm_label = "[green]✓[/green] LLM [dim](Claude Code login)[/dim]"
    else:
        llm_label = "[red]✗[/red] LLM [dim](no auth — agent mode will prompt)[/dim]"

    table.add_row(
        "Agent runtime",
        " · ".join([
            llm_label,
            _badge("Claude Code CLI", status["claude_cli"], "claude.ai/code"),
        ]),
    )
    table.add_row(
        "Integrations",
        " · ".join([
            _badge("Notion", status["notion_key"], "litmus connect notion"),
            _badge("Linear", status["linear_key"], "litmus connect linear"),
        ]),
    )
    if status.get("dbt_project"):
        table.add_row("dbt project", f"detected at [cyan]{status['dbt_project']}[/cyan]")
    console.print(table)


# ──────────────────────────────────────────────────────────────────────────
# Bootstrap wizard
# ──────────────────────────────────────────────────────────────────────────


def _bootstrap(status: dict) -> bool:
    console.print()
    console.print("[bold]Setting up a new Litmus project.[/bold]")

    if not status["claude_cli"]:
        console.print(
            "\n[yellow]Heads up: Claude Code isn't installed.[/yellow]"
        )
        console.print(
            "[dim]The agent-team flow needs it. Install (free) at "
            "https://claude.ai/code, then re-run `litmus`.[/dim]\n"
        )
        if not click.confirm("Continue setup anyway?", default=True):
            return False

    try:
        default_name = Path.cwd().resolve().name or "litmus-project"
        project_name = click.prompt(
            "  Project name", default=default_name
        ).strip() or default_name

        console.print()
        console.print(
            "[dim]  Sample data: customers + markets + transactions "
            "(real star-schema, 30/5/118 rows).[/dim]"
        )
        load_sample = click.confirm("  Load the sample ontology?", default=True)

        console.print()
        warehouse_config = _collect_warehouse_choice()

        dbt_integration = False
        dbt_path = status.get("dbt_project")
        if dbt_path:
            console.print()
            console.print(
                f"[dim]  Detected a dbt project at [cyan]{dbt_path}[/cyan].[/dim]"
            )
            dbt_integration = click.confirm(
                "  Integrate Litmus on top of it?", default=True
            )

        console.print()
        orchestrator = click.prompt(
            "  Existing orchestrator?",
            type=click.Choice(
                ["none", "cron", "airflow", "dagster", "prefect", "github-actions"],
                case_sensitive=False,
            ),
            default="none",
        )

        console.print()
        configure_keys = click.confirm(
            "  Configure Notion / Linear keys now? (skip and run "
            "`litmus connect` later)",
            default=False,
        )
        notion_key = linear_key = anthropic_key = ""
        if configure_keys:
            console.print()
            notion_key = _prompt_secret(
                "    Notion API key", "https://notion.so/profile/integrations"
            )
            linear_key = _prompt_secret(
                "    Linear API key", "https://linear.app/settings/api"
            )
            anthropic_key = _prompt_secret(
                "    Anthropic API key (LLM for agent mode — skip if logged into Claude Code)",
                "https://console.anthropic.com/settings/keys",
            )

    except (KeyboardInterrupt, click.exceptions.Abort):
        console.print("\n[yellow]Cancelled. Nothing was written.[/yellow]")
        return False

    # ─── Execute ───
    console.print()
    cwd = Path.cwd().resolve()

    try:
        for sub in (
            "data", "data/raw", "pipelines", "transforms",
            "metrics", "dashboards", "semantic",
        ):
            (cwd / sub).mkdir(parents=True, exist_ok=True)
        console.print("  [green]✓[/green] project directories")
    except PermissionError as e:
        console.print(f"  [red]✗[/red] permission denied creating dirs: {e}")
        return False

    scaffold = _install_agent_scaffold(cwd)
    if scaffold["agents"] or scaffold["skills"] or scaffold["mcp"]:
        bits = []
        if scaffold["agents"]:
            bits.append(f"{scaffold['agents']} agents")
        if scaffold["skills"]:
            bits.append(f"{scaffold['skills']} skills")
        if scaffold["mcp"]:
            bits.append("MCP config")
        console.print(f"  [green]✓[/green] {', '.join(bits)} in .claude/")

    env_changes = {}
    if notion_key:
        env_changes["NOTION_API_KEY"] = notion_key
    if linear_key:
        env_changes["LINEAR_API_KEY"] = linear_key
    if anthropic_key:
        # Save both names — Claude Code reads ANTHROPIC_API_KEY, the trust
        # engine reads LITMUS_ANTHROPIC_API_KEY. Same value either way.
        env_changes["ANTHROPIC_API_KEY"] = anthropic_key
        env_changes["LITMUS_ANTHROPIC_API_KEY"] = anthropic_key
    for k, v in warehouse_config.get("env", {}).items():
        env_changes[k] = v
    if env_changes:
        _write_env_file(env_changes)
        console.print(f"  [green]✓[/green] wrote .env ({len(env_changes)} keys)")

    sample_loaded_ok = False
    if load_sample:
        sample_loaded_ok = _run_sample_load()

    state = _load_state()
    state.update({
        "initialized": True,
        "project_name": project_name,
        "warehouse_type": warehouse_config["type"],
        "warehouse_url": warehouse_config["url"],
        "warehouse_meta": warehouse_config.get("meta", {}),
        "dbt_integration": bool(dbt_integration),
        "dbt_project_path": str(dbt_path) if dbt_path and dbt_integration else None,
        "orchestrator": orchestrator,
        "sample_loaded": sample_loaded_ok,
        "version": __version__,
    })
    _save_state(state)
    console.print(f"  [green]✓[/green] wrote {STATE_FILE}")
    return True


def _collect_warehouse_choice() -> dict:
    choice = click.prompt(
        "  Warehouse",
        type=click.Choice(
            ["duckdb", "postgres", "snowflake", "bigquery"], case_sensitive=False
        ),
        default="duckdb",
    )

    if choice == "duckdb":
        return {
            "type": "duckdb",
            "url": "duckdb:///./data/warehouse.duckdb",
            "meta": {},
            "env": {},
        }

    if choice == "postgres":
        host = click.prompt("    Host", default="localhost")
        port = click.prompt("    Port", default="5432")
        database = click.prompt("    Database")
        user = click.prompt("    Username")
        password = _prompt_secret("    Password")
        return {
            "type": "postgres",
            "url": f"postgresql://{user}@{host}:{port}/{database}",
            "meta": {"host": host, "port": port, "database": database, "user": user},
            "env": {"LITMUS_WAREHOUSE_PASSWORD": password} if password else {},
        }

    if choice == "snowflake":
        account = click.prompt("    Snowflake account")
        database = click.prompt("    Database")
        schema = click.prompt("    Schema", default="PUBLIC")
        warehouse = click.prompt("    Warehouse (compute)", default="COMPUTE_WH")
        user = click.prompt("    Username")
        password = _prompt_secret("    Password")
        return {
            "type": "snowflake",
            "url": (
                f"snowflake://{user}@{account}/{database}/{schema}"
                f"?warehouse={warehouse}"
            ),
            "meta": {
                "account": account, "database": database, "schema": schema,
                "warehouse": warehouse, "user": user,
            },
            "env": {"LITMUS_WAREHOUSE_PASSWORD": password} if password else {},
        }

    if choice == "bigquery":
        project = click.prompt("    GCP project id")
        dataset = click.prompt("    BigQuery dataset", default="analytics")
        creds_path = click.prompt(
            "    Service account JSON path",
            default="~/.config/gcloud/litmus-bq.json",
        )
        creds_resolved = str(Path(creds_path).expanduser().resolve())
        return {
            "type": "bigquery",
            "url": f"bigquery://{project}/{dataset}",
            "meta": {"project": project, "dataset": dataset, "creds": creds_resolved},
            "env": {"GOOGLE_APPLICATION_CREDENTIALS": creds_resolved},
        }

    raise click.UsageError(f"Unknown warehouse: {choice}")


def _prompt_secret(label: str, help_url: str = "") -> str:
    if help_url:
        console.print(f"[dim]    →  Get one at {help_url}[/dim]")
    raw: str = click.prompt(
        label, default="", show_default=False, hide_input=True
    )
    return raw.strip()


def _run_sample_load() -> bool:
    warehouse = "duckdb:///./data/warehouse.duckdb"
    try:
        from litmus.pipelines.sample import load_sample
        load_sample(warehouse)
        console.print("  [green]✓[/green] sample data copied")
    except Exception as e:
        console.print(f"  [red]✗[/red] sample data copy failed: {e}")
        return False

    try:
        from litmus.pipelines.runner import run_all
        run_all(warehouse)
        console.print("  [green]✓[/green] pipelines + transforms run")
        return True
    except Exception as e:
        console.print(f"  [red]✗[/red] sample pipeline run failed: {e}")
        warehouse_file = Path("data/warehouse.duckdb")
        try:
            if warehouse_file.exists():
                warehouse_file.unlink()
                console.print(
                    "  [dim]cleaned up partial warehouse — re-run "
                    "`litmus demo` to retry[/dim]"
                )
        except OSError:
            pass
        return False


def _write_env_file(values: dict[str, str]) -> None:
    env_path = Path(".env")
    existing: dict[str, str] = {}
    if env_path.exists():
        for line in env_path.read_text().splitlines():
            if "=" in line and not line.lstrip().startswith("#"):
                k, _, v = line.partition("=")
                existing[k.strip()] = v.strip()
    existing.update(values)

    header = (
        "# Litmus environment\n"
        "# Generated by `litmus` setup. Edit by hand any time.\n\n"
    )
    body = "\n".join(f"{k}={v}" for k, v in existing.items()) + "\n"
    env_path.write_text(header + body)
    try:
        env_path.chmod(0o600)
    except OSError:
        pass

    gitignore = Path(".gitignore")
    if gitignore.exists():
        contents = gitignore.read_text()
        present = any(
            line.strip() == ".env"
            for line in contents.splitlines()
            if line.strip() and not line.lstrip().startswith("#")
        )
        if not present:
            gitignore.write_text(contents.rstrip() + "\n.env\n")
    else:
        gitignore.write_text(".env\n")


# ──────────────────────────────────────────────────────────────────────────
# Agent-mode REPL — the default landing after bootstrap
# ──────────────────────────────────────────────────────────────────────────


SLASH_COMMANDS = [
    ("/assets", "list tables + semantic descriptions"),
    ("/health", "trust check status + pipeline freshness"),
    ("/dashboards", "list dashboards + open one"),
    ("/chart <q>", "scaffold a one-page chart for <q>"),
    ("/menu", "drop into the classic numbered menu"),
    ("/help", "show this list"),
    ("/exit", "quit (Ctrl-D also works)"),
]


def _agent_repl(status: dict) -> None:
    """Chat-style REPL — the default mode after bootstrap.

    Free text goes to ``claude --print``. Lines starting with / are
    slash commands handled locally. Auth is gated up front via
    ``_ensure_llm_auth``.
    """
    if not _ensure_llm_auth(status):
        return

    _print_agent_help(opening=True)

    while True:
        try:
            line = click.prompt(
                click.style(">", fg="cyan", bold=True),
                default="",
                show_default=False,
                prompt_suffix=" ",
            )
        except (KeyboardInterrupt, click.exceptions.Abort, EOFError):
            console.print()
            return

        line = line.strip()
        if not line:
            continue

        if line in ("/exit", "/quit", ":q", "exit", "quit"):
            return

        if line == "/help":
            _print_agent_help()
            continue

        if line == "/menu":
            _legacy_menu_loop()
            continue

        if line == "/assets":
            _action_assets()
            continue

        if line == "/health":
            _action_health()
            continue

        if line == "/dashboards":
            _action_dashboards_list()
            continue

        if line.startswith("/chart"):
            arg = line[len("/chart"):].strip()
            _action_chart(arg)
            continue

        # Unknown slash command — be helpful.
        if line.startswith("/"):
            console.print(
                f"[yellow]Unknown command: {line}[/yellow]  "
                "Try [cyan]/help[/cyan]"
            )
            continue

        # Anything else → agent.
        _ask_agent(line, status)


def _ensure_llm_auth(status: dict) -> bool:
    """Make sure we can talk to an LLM. Prompts once if neither auth is set.

    Resolution order:
    1. ``ANTHROPIC_API_KEY`` in env (set externally or loaded from .env)
    2. Claude Code installed + ``~/.claude/`` config dir present (= OAuth'd in)
    3. Prompt the user — paste key or skip (assumes Claude Code login).

    Returns False only if the user explicitly cancels.
    """
    llm = status.get("llm_auth") or _llm_auth_state()
    if llm["ready"]:
        return True

    console.print()
    console.print(
        "[bold yellow]Agent mode needs LLM access.[/bold yellow]"
    )
    console.print("[dim]Pick one:[/dim]")
    console.print(
        "[dim]  1. Sign in to Claude Code (free, included in your subscription) "
        "→ [cyan]https://claude.ai/code[/cyan][/dim]"
    )
    console.print(
        "[dim]  2. Paste an Anthropic API key (pay-as-you-go) "
        "→ [cyan]https://console.anthropic.com/settings/keys[/cyan][/dim]"
    )
    console.print()

    try:
        key = click.prompt(
            "Paste API key (or Enter to use Claude Code login)",
            default="",
            show_default=False,
            hide_input=True,
        ).strip()
    except (KeyboardInterrupt, click.exceptions.Abort, EOFError):
        console.print("\n[yellow]Cancelled.[/yellow]")
        return False

    state = _load_state()

    if key:
        # Save as both names — ANTHROPIC_API_KEY is what Claude Code reads,
        # LITMUS_ANTHROPIC_API_KEY is what the trust engine's run-explanation
        # feature reads. Same value, same .env, no surprises.
        _write_env_file({
            "ANTHROPIC_API_KEY": key,
            "LITMUS_ANTHROPIC_API_KEY": key,
        })
        os.environ["ANTHROPIC_API_KEY"] = key
        os.environ["LITMUS_ANTHROPIC_API_KEY"] = key
        state["llm_auth_method"] = "api_key"
        _save_state(state)
        console.print("  [green]✓[/green] saved key to .env (chmod 600)")
        return True

    # User opted to use Claude Code login. Verify the binary at least exists;
    # if it doesn't, we can't continue.
    if not shutil.which("claude"):
        console.print(
            "\n[red]No API key and no Claude Code installed.[/red]"
        )
        console.print(
            "[dim]Install from https://claude.ai/code, then re-run "
            "[cyan]litmus[/cyan].[/dim]"
        )
        return False

    state["llm_auth_method"] = "claude_code"
    _save_state(state)
    console.print(
        "[dim]Continuing with your Claude Code login. "
        "If agent mode says 'not authenticated', run `claude` once "
        "to sign in.[/dim]"
    )
    return True


def _print_agent_help(opening: bool = False) -> None:
    console.print()
    if opening:
        console.print("[bold green]Agent mode.[/bold green]  "
                      "[dim]Type a question, or use a slash command:[/dim]")
    else:
        console.print("[bold]Slash commands:[/bold]")
    for cmd, desc in SLASH_COMMANDS:
        console.print(f"  [cyan]{cmd:<14}[/cyan] [dim]{desc}[/dim]")
    if opening:
        console.print()
        console.print(
            "[dim]Examples: \"what's our top market by revenue\", "
            '"@analyst show me MoM growth"[/dim]'
        )


def _ask_agent(prompt: str, status: dict) -> None:
    """Send a free-text prompt to the agent team via `claude --print`."""
    if not status["claude_cli"]:
        console.print(
            "\n[yellow]Claude Code isn't installed.[/yellow] Get it at "
            "[cyan]https://claude.ai/code[/cyan] (free), then re-run `litmus`."
        )
        return

    _install_agent_scaffold(Path.cwd())
    state = _load_state()

    skip_perms = (
        os.environ.get(SKIP_PERMS_ENV) == "1"
        or state.get("skip_agent_perms") is True
    )
    if not skip_perms and not state.get("skip_agent_perms_asked"):
        console.print()
        console.print(
            "[dim]Litmus can let the agents read/write/run files in this "
            "directory without per-tool prompts.[/dim]"
        )
        console.print(
            "[dim]Convenient but means an agent could edit any file. "
            "Off by default.[/dim]"
        )
        skip_perms = click.confirm("Skip per-tool prompts in this project?", default=False)
        state["skip_agent_perms"] = skip_perms
        state["skip_agent_perms_asked"] = True
        _save_state(state)

    console.print()
    console.print("[dim]Working...[/dim]\n")

    from litmus.runtime import claude_model_args, runtime_note

    note = runtime_note()
    if note:
        console.print(f"[dim]{note}[/dim]")

    cmd = [
        "claude",
        "--print",
        prompt,
        "--append-system-prompt", DATA_ENGINEERING_SCOPE,
    ]
    cmd += claude_model_args()
    if skip_perms:
        cmd.append("--allow-dangerously-skip-permissions")

    try:
        subprocess.run(cmd)
    except FileNotFoundError:
        console.print("\n[red]Couldn't launch `claude`. Run `litmus doctor`.[/red]")
    except KeyboardInterrupt:
        console.print("\n[yellow]Cancelled.[/yellow]")


# ──────────────────────────────────────────────────────────────────────────
# Local slash commands (deterministic, no LLM)
# ──────────────────────────────────────────────────────────────────────────


def _action_assets() -> None:
    """List tables in the warehouse, joined with semantic descriptions."""
    state = _load_state()
    warehouse_url = state.get(
        "warehouse_url", "duckdb:///./data/warehouse.duckdb"
    )
    semantic = _load_semantic_layer()

    if not warehouse_url.startswith("duckdb://"):
        console.print(
            f"\n[yellow]Warehouse type {state.get('warehouse_type')} not "
            f"introspectable yet.[/yellow]"
        )
        return

    db_path = warehouse_url.replace("duckdb:///", "").replace("duckdb://", "")
    if not Path(db_path).exists():
        console.print(
            "\n[yellow]No warehouse yet.[/yellow]  Run `litmus demo` to "
            "load the sample, or `litmus add <csv>` to register a source."
        )
        return

    try:
        import duckdb
        con = duckdb.connect(db_path, read_only=True)
        tables = con.execute(
            "SELECT table_name FROM information_schema.tables "
            "WHERE table_schema = 'main' ORDER BY table_name"
        ).fetchall()
    except Exception as e:
        console.print(f"\n[red]Could not read warehouse: {e}[/red]")
        return

    if not tables:
        console.print(
            "\n[yellow]Warehouse is empty.[/yellow]  Run `litmus demo` "
            "to load the sample."
        )
        return

    table_to_entity = {e.get("table"): e for e in semantic.values()}

    console.print()
    out = Table(title="Tables", show_header=True, header_style="bold")
    out.add_column("Table", style="cyan")
    out.add_column("Rows", justify="right", style="dim")
    out.add_column("Entity", style="green")
    out.add_column("Description", style="dim")
    for (tname,) in tables:
        try:
            (count,) = con.execute(f'SELECT COUNT(*) FROM "{tname}"').fetchone()
        except Exception:
            count = "?"
        ent = table_to_entity.get(tname, {})
        out.add_row(
            tname,
            f"{count:,}" if isinstance(count, int) else str(count),
            ent.get("entity", "—"),
            (ent.get("description") or "")[:60],
        )
    console.print(out)

    if semantic:
        console.print()
        sem = Table(title="Semantic entities", show_header=True, header_style="bold")
        sem.add_column("Entity", style="green")
        sem.add_column("Kind", style="dim")
        sem.add_column("Table", style="cyan")
        sem.add_column("Measures", style="dim")
        for ent in semantic.values():
            measures = [m["name"] for m in ent.get("measures") or []]
            sem.add_row(
                ent.get("entity", "?"),
                ent.get("kind", "?"),
                ent.get("table", "?"),
                ", ".join(measures) if measures else "—",
            )
        console.print(sem)
    else:
        console.print(
            "\n[dim]No semantic layer yet. Drop yaml files into [cyan]semantic/[/cyan] "
            "or ask [cyan]@data-architect[/cyan] to draft them.[/dim]"
        )


def _load_semantic_layer() -> dict:
    """Read semantic/*.yaml into {entity_name: spec_dict}."""
    semantic_dir = Path("semantic")
    if not semantic_dir.exists():
        return {}
    out: dict = {}
    for f in semantic_dir.glob("*.yaml"):
        try:
            spec = yaml.safe_load(f.read_text()) or {}
            name = spec.get("entity") or f.stem
            out[name] = spec
        except yaml.YAMLError:
            continue
    return out


def _action_health() -> None:
    """Data tests + pipeline last-run summary."""
    state = _load_state()
    warehouse_url = state.get(
        "warehouse_url", "duckdb:///./data/warehouse.duckdb"
    )

    tests_dir = Path("tests")
    pipelines_dir = Path("pipelines")

    console.print()
    console.print("[bold]Data tests[/bold]")
    test_files = sorted(tests_dir.glob("*.sql")) if tests_dir.exists() else []
    if not test_files:
        console.print("  [dim]No tests/ yet — ask the team or run `litmus test`.[/dim]")
    elif not warehouse_url.startswith("duckdb://"):
        console.print(
            f"  [dim]{len(test_files)} test(s); non-DuckDB warehouse — run "
            "`litmus test`.[/dim]"
        )
    else:
        import duckdb
        db_path = warehouse_url.replace("duckdb:///", "").replace("duckdb://", "")
        for tf in test_files:
            try:
                con = duckdb.connect(db_path, read_only=True)
                rows = con.execute(tf.read_text()).fetchall()
                con.close()
                if rows:
                    console.print(f"  [red]✗[/red] {tf.stem} ({len(rows)} problem row(s))")
                else:
                    console.print(f"  [green]✓[/green] {tf.stem}")
            except Exception as e:
                console.print(f"  [red]✗[/red] {tf.stem}: {e}")

    console.print()
    console.print("[bold]Pipelines[/bold]")
    if not pipelines_dir.exists() or not any(pipelines_dir.glob("*.yaml")):
        console.print("  [dim]No pipelines/ yet.[/dim]")
        return
    for p in sorted(pipelines_dir.glob("*.yaml")):
        # Heuristic: check raw table exists and report its row count.
        try:
            spec = yaml.safe_load(p.read_text()) or {}
            tbl = spec.get("target", {}).get("table", f"raw_{p.stem}")
            if warehouse_url.startswith("duckdb://"):
                import duckdb
                db_path = warehouse_url.replace("duckdb:///", "").replace("duckdb://", "")
                if Path(db_path).exists():
                    con = duckdb.connect(db_path, read_only=True)
                    (count,) = con.execute(f'SELECT COUNT(*) FROM "{tbl}"').fetchone()
                    console.print(
                        f"  [green]✓[/green] {p.stem:<20} → {tbl} "
                        f"[dim]({count:,} rows)[/dim]"
                    )
                else:
                    console.print(f"  [yellow]?[/yellow] {p.stem:<20} → warehouse missing")
            else:
                console.print(f"  [dim]?[/dim] {p.stem:<20} → {tbl} (non-DuckDB; skip)")
        except Exception as e:
            console.print(f"  [red]✗[/red] {p.stem}: {e}")


def _action_dashboards_list() -> None:
    dashboards_dir = Path("dashboards")
    if not dashboards_dir.exists() or not any(dashboards_dir.glob("*.py")):
        console.print(
            "\n[yellow]No dashboards yet.[/yellow]  Try "
            "[cyan]/chart show me revenue by market[/cyan]."
        )
        return
    dashboards = sorted(dashboards_dir.glob("*.py"))
    console.print()
    console.print(f"[bold]Dashboards ({len(dashboards)})[/bold]")
    for i, d in enumerate(dashboards, 1):
        console.print(f"  [cyan]{i}.[/cyan] {d.name}")
    console.print()
    try:
        choice = click.prompt(
            "Open which (number, or Enter to skip)",
            default="", show_default=False,
        ).strip()
    except (KeyboardInterrupt, click.exceptions.Abort):
        return
    if not choice:
        return
    try:
        idx = int(choice) - 1
        target = dashboards[idx]
    except (ValueError, IndexError):
        console.print("[yellow]Not a valid choice.[/yellow]")
        return

    console.print(f"\nStarting Streamlit (serving [cyan]{target}[/cyan])...")
    try:
        subprocess.run([sys.executable, "-m", "streamlit", "run", str(target)])
    except FileNotFoundError:
        console.print(
            "[red]streamlit not installed.[/red] "
            "Run: `uv tool install --reinstall litmus-data`"
        )


def _action_chart(question: str) -> None:
    """Proxy /chart to the analyst agent."""
    if not question:
        console.print(
            "\n[yellow]Usage:[/yellow] [cyan]/chart <description>[/cyan]"
        )
        console.print(
            "[dim]e.g. /chart show me weekly revenue by market[/dim]"
        )
        return

    status = _project_status()
    prompt = (
        "@analyst Build a one-page Streamlit dashboard that answers this "
        f"question: {question!r}.\n\n"
        "Constraints:\n"
        "- Read only from mart_* tables (or join via raw_* if no mart exists).\n"
        "- Save as dashboards/chart_<slug>.py with a descriptive filename.\n"
        "- Use the semantic/ definitions to resolve metric names.\n"
        "- Include freshness_header from litmus.dashboards.\n"
        "- After writing the file, print the path so I can open it.\n"
    )
    _ask_agent(prompt, status)


# ──────────────────────────────────────────────────────────────────────────
# Legacy menu (reachable via /menu) — kept for power users + scripts
# ──────────────────────────────────────────────────────────────────────────


def _legacy_menu_loop() -> None:
    while True:
        status = _project_status()
        console.print()
        console.print("[bold]Menu[/bold] [dim](classic; type /agent or q to leave)[/dim]")
        console.print("  [cyan]1[/cyan]. Ask an agent a question")
        console.print("  [cyan]2[/cyan]. Open a dashboard")
        console.print("  [cyan]3[/cyan]. Run trust checks")
        console.print("  [cyan]4[/cyan]. Re-run all pipelines + transforms")
        console.print("  [cyan]5[/cyan]. Project doctor")
        console.print("  [cyan]q[/cyan]. Back to agent mode")
        try:
            choice = click.prompt(
                "Choose",
                type=click.Choice(["1", "2", "3", "4", "5", "q"], case_sensitive=False),
                default="q",
                show_choices=False,
            ).lower()
        except (KeyboardInterrupt, click.exceptions.Abort):
            return

        if choice == "q":
            return
        elif choice == "1":
            try:
                q = click.prompt("?", default="", show_default=False).strip()
            except (KeyboardInterrupt, click.exceptions.Abort):
                continue
            if q:
                _ask_agent(q, status)
        elif choice == "2":
            _action_dashboards_list()
        elif choice == "3":
            _action_health()
        elif choice == "4":
            from litmus.pipelines.runner import run_all
            run_all()
        elif choice == "5":
            from litmus.diagnostics import run_doctor
            run_doctor()


# ──────────────────────────────────────────────────────────────────────────
# Entry point
# ──────────────────────────────────────────────────────────────────────────


def run_tui() -> None:
    # Load .env first so anything the user previously saved (API keys,
    # warehouse creds) shows up in os.environ before status checks run.
    _load_dotenv()

    _print_banner()
    console.print()

    status = _project_status()
    _print_project_summary(status)

    if not status["initialized"]:
        if not _bootstrap(status):
            console.print(
                "\n[dim]Setup cancelled. Run [cyan]litmus[/cyan] any time to retry.[/dim]"
            )
            return
        status = _project_status()

    # Land directly in agent mode.
    _agent_repl(status)


def is_tty() -> bool:
    return sys.stdin.isatty() and sys.stdout.isatty()
