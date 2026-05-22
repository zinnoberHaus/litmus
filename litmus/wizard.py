"""``litmus init`` — the guided setup wizard that builds your AI data team.

Flow:

    project name
      → pick an AI model
      → choose data inflow (multi-select)
      → build the "Litmus house" (progress bar)
      → done

Everything the wizard writes is generated *from the user's choices* — the
source configs, the project context the agents read, and the starter
transform / dashboard / test are parameterized by the data sources picked.

No trust engine, no DSL. The output is a plain, agent-driven data project:
sources you verify, transforms that hold your business logic, dashboards that
visualize, and lightweight SQL tests that guard the result.
"""

from __future__ import annotations

import json
import shutil
import time
from dataclasses import dataclass, field
from pathlib import Path

import click
import yaml
from rich.console import Console
from rich.panel import Panel
from rich.progress import BarColumn, Progress, SpinnerColumn, TextColumn
from rich.table import Table

from litmus import __version__
from litmus.scaffold import install_agent_team

console = Console()


# ──────────────────────────────────────────────────────────────────────────
# Registries — the menus the wizard offers
# ──────────────────────────────────────────────────────────────────────────


@dataclass(frozen=True)
class ModelChoice:
    id: str
    label: str
    provider: str  # anthropic | openai | google | local
    model: str  # the API/model identifier written to config
    runtime: str  # claude-code | agent-sdk | api
    note: str = ""


# Curated menu of well-known models. Claude paths are fully wired; the others
# are written to config and run through provider adapters (Phase 5) — flagged
# "preview" so the menu stays honest.
MODELS: list[ModelChoice] = [
    ModelChoice(
        "claude-opus", "Claude Opus 4.7", "anthropic", "claude-opus-4-7",
        "claude-code", "most capable; best for the architect/builder roles",
    ),
    ModelChoice(
        "claude-sonnet", "Claude Sonnet 4.6", "anthropic", "claude-sonnet-4-6",
        "claude-code", "fast + strong; a good default",
    ),
    ModelChoice(
        "claude-haiku", "Claude Haiku 4.5", "anthropic", "claude-haiku-4-5-20251001",
        "claude-code", "cheapest; quick edits and Q&A",
    ),
    ModelChoice(
        "gpt-5", "GPT-5 (OpenAI)", "openai", "gpt-5",
        "api", "preview — needs OPENAI_API_KEY + adapter",
    ),
    ModelChoice(
        "gemini-pro", "Gemini 2.5 Pro (Google)", "google", "gemini-2.5-pro",
        "api", "preview — needs GOOGLE_API_KEY + adapter",
    ),
    ModelChoice(
        "local", "Local model (Ollama / LM Studio)", "local", "llama3.1",
        "api", "preview — points at a local OpenAI-compatible endpoint",
    ),
]

_DEFAULT_MODEL = "claude-sonnet"


@dataclass(frozen=True)
class SourceChoice:
    id: str
    label: str
    kind: str  # how the ingest layer treats it
    env_keys: list[str] = field(default_factory=list)
    note: str = ""

    def default_config(self) -> dict:
        """The sources/<id>.yaml stub written for this source."""
        base: dict = {"id": self.id, "type": self.kind}
        if self.kind == "sample":
            base["description"] = "Bundled sample dataset (customers / markets / transactions)"
        elif self.kind == "duckdb":
            base["url"] = "duckdb:///./data/warehouse.duckdb"
        elif self.kind == "postgres":
            base.update(host="${PGHOST}", port=5432, database="${PGDATABASE}",
                        user="${PGUSER}", password="${PGPASSWORD}")
        elif self.kind == "snowflake":
            base.update(account="${SNOWFLAKE_ACCOUNT}", database="${SNOWFLAKE_DB}",
                        schema="PUBLIC", warehouse="COMPUTE_WH",
                        user="${SNOWFLAKE_USER}", password="${SNOWFLAKE_PASSWORD}")
        elif self.kind == "bigquery":
            base.update(project="${GCP_PROJECT}", dataset="analytics",
                        credentials="${GOOGLE_APPLICATION_CREDENTIALS}")
        elif self.kind == "csv":
            base.update(path="./data/raw/", glob="*.csv")
        elif self.kind == "rest":
            base.update(base_url="${API_BASE_URL}", auth="bearer", token="${API_TOKEN}")
        elif self.kind == "stripe":
            base.update(api_key="${STRIPE_API_KEY}", objects=["charges", "customers"])
        elif self.kind == "sheets":
            base.update(spreadsheet_id="${SHEET_ID}",
                        credentials="${GOOGLE_APPLICATION_CREDENTIALS}")
        return base


SOURCES: list[SourceChoice] = [
    SourceChoice("sample", "Sample dataset", "sample", [],
                 "30 customers / 5 markets / 118 transactions — zero setup"),
    SourceChoice("warehouse", "DuckDB (local file)", "duckdb", [],
                 "zero-config local warehouse"),
    SourceChoice("postgres", "PostgreSQL", "postgres",
                 ["PGHOST", "PGDATABASE", "PGUSER", "PGPASSWORD"]),
    SourceChoice("snowflake", "Snowflake", "snowflake",
                 ["SNOWFLAKE_ACCOUNT", "SNOWFLAKE_DB", "SNOWFLAKE_USER", "SNOWFLAKE_PASSWORD"]),
    SourceChoice("bigquery", "BigQuery", "bigquery",
                 ["GCP_PROJECT", "GOOGLE_APPLICATION_CREDENTIALS"]),
    SourceChoice("csv", "CSV files", "csv", []),
    SourceChoice("rest", "REST API", "rest", ["API_BASE_URL", "API_TOKEN"]),
    SourceChoice("stripe", "Stripe", "stripe", ["STRIPE_API_KEY"]),
    SourceChoice("sheets", "Google Sheets", "sheets",
                 ["SHEET_ID", "GOOGLE_APPLICATION_CREDENTIALS"]),
]

_DEFAULT_SOURCES = ["sample", "warehouse"]


# ──────────────────────────────────────────────────────────────────────────
# Public entry point
# ──────────────────────────────────────────────────────────────────────────


def run_wizard(
    target: Path,
    *,
    skip_prompts: bool = False,
    project_name: str | None = None,
    model_id: str | None = None,
    source_ids: list[str] | None = None,
    force: bool = False,
) -> dict:
    """Run the setup wizard and build the project in ``target``.

    Returns the project state dict (also written to ``.litmus/state.json``).
    Flags let the CLI pre-fill answers and run non-interactively (``--yes``).
    """
    target = Path(target)
    interactive = not skip_prompts

    if interactive:
        _banner()

    # 1. Project name
    name = project_name or (target.resolve().name or "litmus-project")
    if interactive and project_name is None:
        name = click.prompt("Project name", default=name).strip() or name

    # 2. Model
    model = _resolve_model(model_id, interactive)

    # 3. Data inflow (multi-select)
    sources = _resolve_sources(source_ids, interactive)

    # 4. Build the house (progress bar)
    config = {
        "project_name": name,
        "model": {
            "provider": model.provider,
            "name": model.model,
            "runtime": model.runtime,
        },
        "sources": [s.id for s in sources],
        "version": __version__,
        "created_by": "litmus init",
    }
    _build_house(target, config, sources, model, force=force)

    # 5. Done
    if interactive:
        _print_next_steps(name, sources)
    return config


def reconfigure(target: Path) -> dict:
    """Re-run the model + sources picks against an existing project (``litmus configure``)."""
    target = Path(target)
    cfg_path = target / "litmus.yaml"
    if not cfg_path.exists():
        console.print("[yellow]No litmus.yaml here — run `litmus init` first.[/yellow]")
        return {}

    existing = yaml.safe_load(cfg_path.read_text()) or {}
    name = existing.get("project_name") or (target.resolve().name or "litmus-project")
    console.print(f"[bold]Reconfiguring {name}[/bold]")

    model = _resolve_model(None, interactive=True)
    sources = _resolve_sources(None, interactive=True)
    config = {
        "project_name": name,
        "model": {
            "provider": model.provider,
            "name": model.model,
            "runtime": model.runtime,
        },
        "sources": [s.id for s in sources],
        "version": __version__,
        "created_by": existing.get("created_by", "litmus init"),
    }
    _write_config(target, config, force=True)
    _write_sources(target, sources, force=True)
    _write_context(target, config, sources, model, force=True)
    _write_env_example(target, sources, model, force=True)
    _write_state(target, config, force=True)
    console.print("  [green]✓[/green] reconfigured")
    return config


# ──────────────────────────────────────────────────────────────────────────
# Steps
# ──────────────────────────────────────────────────────────────────────────


def _banner() -> None:
    console.print()
    console.print(
        Panel.fit(
            "[bold cyan]Litmus[/bold cyan] — your AI data agents team\n"
            "[dim]Let's set up your team and the project around your data.[/dim]",
            border_style="cyan",
        )
    )
    console.print()


def _resolve_model(model_id: str | None, interactive: bool) -> ModelChoice:
    by_id = {m.id: m for m in MODELS}
    if model_id and model_id in by_id:
        return by_id[model_id]
    if not interactive:
        return by_id[_DEFAULT_MODEL]

    console.print("[bold]Pick an AI model[/bold] [dim](powers your agent team)[/dim]")
    table = Table(show_header=True, header_style="bold", box=None, padding=(0, 2))
    table.add_column("#", style="cyan", justify="right")
    table.add_column("Model")
    table.add_column("Notes", style="dim")
    for i, m in enumerate(MODELS, 1):
        default_tag = "  [green](default)[/green]" if m.id == _DEFAULT_MODEL else ""
        table.add_row(str(i), m.label + default_tag, m.note)
    console.print(table)

    default_idx = next(i for i, m in enumerate(MODELS, 1) if m.id == _DEFAULT_MODEL)
    choice = click.prompt(
        "Model number", default=default_idx, type=click.IntRange(1, len(MODELS))
    )
    chosen = MODELS[int(choice) - 1]
    if chosen.runtime == "api":
        console.print(
            f"  [yellow]Note:[/yellow] {chosen.label} runs through a provider adapter "
            "(preview). Claude models work out of the box.\n"
        )
    return chosen


def _resolve_sources(source_ids: list[str] | None, interactive: bool) -> list[SourceChoice]:
    by_id = {s.id: s for s in SOURCES}
    if source_ids:
        picked = [by_id[s] for s in source_ids if s in by_id]
        if picked:
            return picked
    if not interactive:
        return [by_id[s] for s in _DEFAULT_SOURCES]

    console.print("[bold]Choose your data inflow[/bold] "
                  "[dim](one or more — comma-separated)[/dim]")
    table = Table(show_header=True, header_style="bold", box=None, padding=(0, 2))
    table.add_column("#", style="cyan", justify="right")
    table.add_column("Source")
    table.add_column("Notes", style="dim")
    for i, s in enumerate(SOURCES, 1):
        table.add_row(str(i), s.label, s.note or (", ".join(s.env_keys) if s.env_keys else ""))
    console.print(table)

    default_nums = ",".join(
        str(i) for i, s in enumerate(SOURCES, 1) if s.id in _DEFAULT_SOURCES
    )
    while True:
        raw = click.prompt("Source numbers", default=default_nums).strip()
        nums = _parse_multiselect(raw, len(SOURCES))
        if nums:
            return [SOURCES[i - 1] for i in nums]
        console.print("[yellow]Pick at least one (e.g. 1,2).[/yellow]")


def _parse_multiselect(raw: str, n: int) -> list[int]:
    out: list[int] = []
    for tok in raw.replace(" ", "").split(","):
        if not tok:
            continue
        try:
            v = int(tok)
        except ValueError:
            return []
        if 1 <= v <= n and v not in out:
            out.append(v)
    return out


def _build_house(
    target: Path,
    config: dict,
    sources: list[SourceChoice],
    model: ModelChoice,
    *,
    force: bool,
) -> None:
    """Generate the project — the 'Litmus house' — with a progress bar."""
    console.print()
    console.print("[bold]Building your Litmus house...[/bold]")

    steps = [
        ("Creating project folders", lambda: _make_dirs(target)),
        ("Writing litmus.yaml", lambda: _write_config(target, config, force)),
        ("Generating source configs", lambda: _write_sources(target, sources, force)),
        ("Scaffolding transforms / dashboards / tests",
         lambda: _write_frameworks(target, sources, force)),
        ("Installing the agent team", lambda: install_agent_team(target, force=force)),
        ("Writing project context for the agents",
         lambda: _write_context(target, config, sources, model, force)),
        ("Writing .env template", lambda: _write_env_example(target, sources, model, force)),
        ("Saving project state", lambda: _write_state(target, config, force)),
    ]
    if any(s.id == "sample" for s in sources):
        steps.append(("Loading the sample dataset", lambda: _load_sample(target)))

    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        BarColumn(),
        TextColumn("[progress.percentage]{task.percentage:>3.0f}%"),
        console=console,
    ) as progress:
        task = progress.add_task("Setting up...", total=len(steps))
        for desc, fn in steps:
            progress.update(task, description=desc)
            try:
                fn()
            except Exception as exc:  # noqa: BLE001 — report, keep building
                console.print(f"  [yellow]! {desc}: {exc}[/yellow]")
            time.sleep(0.05)  # let the bar render the step
            progress.advance(task)

    console.print("  [green]✓[/green] house built")


# ──────────────────────────────────────────────────────────────────────────
# Generators (the house)
# ──────────────────────────────────────────────────────────────────────────


def _make_dirs(target: Path) -> None:
    for sub in ("sources", "transforms", "dashboards", "tests", "data", "data/raw"):
        (target / sub).mkdir(parents=True, exist_ok=True)


def _w(path: Path, content: str, force: bool) -> None:
    """Write ``content`` to ``path`` unless it exists and ``force`` is False."""
    if path.exists() and not force:
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content)


def _write_config(target: Path, config: dict, force: bool) -> None:
    _w(target / "litmus.yaml", yaml.safe_dump(config, sort_keys=False), force)


def _write_sources(target: Path, sources: list[SourceChoice], force: bool) -> None:
    for s in sources:
        _w(
            target / "sources" / f"{s.id}.yaml",
            yaml.safe_dump(s.default_config(), sort_keys=False),
            force,
        )


def _primary_table(sources: list[SourceChoice]) -> str:
    """Best-guess starting table name for the generated starter files."""
    if any(s.id == "sample" for s in sources):
        return "transactions"
    return "raw_" + sources[0].id


def _write_frameworks(target: Path, sources: list[SourceChoice], force: bool) -> None:
    tbl = _primary_table(sources)

    _w(target / "transforms" / "README.md",
       "# Transforms\n\nBusiness-logic transforms (SQL or Python) that turn raw "
       "source tables into the shapes you actually use. Ask the team:\n\n"
       "    litmus agent \"build a transform that ...\"\n", force)
    _w(target / "transforms" / "example.sql",
       f"-- Starter transform. Replace with your business logic.\n"
       f"-- Reads from the '{tbl}' table that your data inflow lands.\n"
       f"CREATE OR REPLACE TABLE summary AS\n"
       f"SELECT *\nFROM {tbl}\nLIMIT 100;\n", force)

    _w(target / "dashboards" / "README.md",
       "# Dashboards\n\nStreamlit pages that visualize your data. "
       "Build one with `litmus dashboard` or ask the team.\n", force)
    _w(target / "dashboards" / "overview.py",
       _STARTER_DASHBOARD.format(table=tbl), force)

    _w(target / "tests" / "README.md",
       "# Tests\n\nLightweight SQL checks that guard your data — each `.sql` file "
       "is a query that must return zero rows to pass. Run them with `litmus test`.\n", force)
    _w(target / "tests" / "not_empty.sql",
       f"-- FAILS if the table is empty (returns a row when count = 0).\n"
       f"SELECT 1 AS problem WHERE (SELECT COUNT(*) FROM {tbl}) = 0;\n", force)


def _write_context(
    target: Path, config: dict, sources: list[SourceChoice], model: ModelChoice, force: bool
) -> None:
    """A markdown brief the agents read to ground themselves in this project."""
    lines = [
        f"# Project: {config['project_name']}",
        "",
        f"AI model: **{model.label}** (`{model.model}`, runtime `{model.runtime}`)",
        "",
        "## Data sources",
        "",
    ]
    for s in sources:
        creds = f" — env: {', '.join(s.env_keys)}" if s.env_keys else ""
        lines.append(
            f"- **{s.label}** (`{s.id}`, type `{s.kind}`){creds} "
            f"— config in `sources/{s.id}.yaml`"
        )
    lines += [
        "",
        "## How the team works here",
        "",
        "- Verify a source → transform it with business logic → visualize / operate on it.",
        "- Transforms live in `transforms/`, dashboards in `dashboards/`, tests in `tests/`.",
        "- No formal data-contract DSL — tests are plain SQL that must return zero rows.",
        "- Read `sources/*.yaml` before inventing a table; ask the user if a source is unclear.",
        "",
    ]
    _w(target / ".litmus" / "context.md", "\n".join(lines), force)


def _write_env_example(
    target: Path, sources: list[SourceChoice], model: ModelChoice, force: bool
) -> None:
    keys: list[str] = []
    if model.provider == "anthropic":
        keys.append("ANTHROPIC_API_KEY")
    elif model.provider == "openai":
        keys.append("OPENAI_API_KEY")
    elif model.provider == "google":
        keys.append("GOOGLE_API_KEY")
    for s in sources:
        keys.extend(s.env_keys)
    # de-dupe, keep order
    ordered: list[str] = []
    for k in keys:
        if k not in ordered:
            ordered.append(k)
    body = "# Litmus environment — fill in and copy to .env\n"
    body += "# (.env is gitignored; never commit secrets)\n\n"
    body += "\n".join(f"{k}=" for k in ordered) + ("\n" if ordered else "")
    _w(target / ".env.example", body, force)

    gitignore = target / ".gitignore"
    if not gitignore.exists():
        _w(gitignore, ".env\ndata/*.duckdb\n__pycache__/\n", force)


def _write_state(target: Path, config: dict, force: bool) -> None:
    state_file = target / ".litmus" / "state.json"
    if state_file.exists() and not force:
        return
    state = dict(config)
    state["initialized"] = True
    # A concrete warehouse_url helps the runner/REPL default sanely.
    state["warehouse_url"] = "duckdb:///./data/warehouse.duckdb"
    state_file.parent.mkdir(parents=True, exist_ok=True)
    state_file.write_text(json.dumps(state, indent=2))


def _load_sample(target: Path) -> None:
    """Copy the bundled sample CSVs into data/raw/ and load them into DuckDB.

    Self-contained — it does not pull in the old pipelines/metrics layout, just
    the raw tables, so the generated house stays clean.
    """
    from litmus.pipelines.sample import SAMPLE_ROOT

    raw = target / "data" / "raw"
    raw.mkdir(parents=True, exist_ok=True)
    csvs = sorted((SAMPLE_ROOT / "data").glob("*.csv"))
    for csv in csvs:
        shutil.copy(csv, raw / csv.name)

    try:
        import duckdb

        con = duckdb.connect(str(target / "data" / "warehouse.duckdb"))
        for csv in csvs:
            con.execute(
                f'CREATE OR REPLACE TABLE "{csv.stem}" AS '
                "SELECT * FROM read_csv_auto(?)",
                [str(raw / csv.name)],
            )
        con.close()
    except Exception:
        pass  # CSVs are copied regardless; warehouse load is best-effort


def _print_next_steps(name: str, sources: list[SourceChoice]) -> None:
    console.print()
    console.print(f"[bold green]{name} is ready — your AI data team is set up.[/bold green]")
    console.print()
    console.print("[bold]Two ways to work with the team:[/bold]")
    console.print("  1. [cyan]litmus[/cyan]                  talk to the team (interactive)")
    console.print("  2. dbt-style commands, all fronted by the agents:")
    console.print("     [cyan]litmus run[/cyan]              ingest → transform")
    console.print("     [cyan]litmus test[/cyan]             run your data tests")
    console.print("     [cyan]litmus dashboard[/cyan]        build / open a visualization")
    console.print("     [cyan]litmus agent \"<task>\"[/cyan]   dispatch a one-off task")
    console.print("     [cyan]litmus configure[/cyan]        change model / sources")
    creds = sorted({k for s in sources for k in s.env_keys})
    if creds:
        console.print()
        console.print(f"  [dim]Add credentials in .env for: {', '.join(creds)}[/dim]")
    console.print()


_STARTER_DASHBOARD = '''\
"""Starter Streamlit dashboard. Run with: streamlit run dashboards/overview.py"""

import duckdb
import streamlit as st

st.set_page_config(page_title="Overview", layout="wide")
st.title("Overview")

con = duckdb.connect("data/warehouse.duckdb", read_only=True)
try:
    df = con.execute("SELECT * FROM {table} LIMIT 1000").df()
    st.metric("Rows (sampled)", len(df))
    st.dataframe(df, use_container_width=True)
except Exception as exc:  # noqa: BLE001
    st.warning(f"No '{table}' table yet — run `litmus run` first. ({{exc}})")
'''
