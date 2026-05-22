# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project

**Litmus** — your AI data agents team, in any repo. A user installs the CLI (`pipx install litmus-data`), runs `litmus init`, walks a short wizard (project name → pick an AI model → choose data inflow → build the project), and gets a data project plus a team of agents that do the work: verify a source, transform it with business logic, visualize it, and test it.

Two audiences: companies with no data team, and product/business teams that don't want centralized data and just need to verify a source → transform → operate. There is **no trust-contract DSL** — that was removed in v0.5 (see `REFACTOR_VISION.md`). Tests are plain SQL files that must return zero rows.

Published on PyPI as **`litmus-data`**; import name and CLI entry point are **`litmus`** (`litmus.cli:main`). Python **3.10+**.

## Common commands

```bash
pip install -e ".[dev]"   # editable install with dev extras
make check                # ruff + mypy + pytest (run before committing)
make test                 # pytest tests/ -v
make lint                 # ruff check + mypy on litmus/
make format               # ruff format + ruff check --fix

pytest tests/test_cli.py            # the CLI / wizard tests
pytest tests/test_cli.py -k Init    # just the init-wizard tests

# Exercise the CLI:
litmus init . --yes --source sample   # build a project non-interactively
litmus test                           # run tests/*.sql
litmus run                            # ingest -> transform
litmus dashboard                      # open Streamlit
```

## Architecture

Litmus is a CLI that scaffolds an agent-driven data project and then fronts every command with the agent team. The package is small and flat:

```
litmus/
├── cli.py            # Click app — all subcommands (entry point litmus.cli:main)
├── wizard.py         # `litmus init` wizard + the scaffolder ("build the Litmus house")
├── tui.py            # bare `litmus` → interactive agent REPL (shells to Claude Code)
├── scaffold.py       # install_agent_team(): copies .claude/ + .mcp.json + AGENTS.md
├── diagnostics.py    # `litmus doctor`
├── pipelines/
│   ├── runner.py     # YAML ingest (pipelines/*.yaml) + SQL transforms (transforms/*.sql)
│   └── sample.py     # locates the bundled sample dataset (SAMPLE_ROOT)
├── dashboards/__init__.py   # Streamlit helper (freshness_header)
├── integrations/     # notion.py / linear.py — payload shapes for the MCP servers
└── templates/        # ships in the wheel:
    ├── AGENTS.md, mcp.json
    ├── claude/agents/*.md, claude/skills/*/SKILL.md
    └── sample_pipeline/data/*.csv   # the sample dataset
```

### `litmus/wizard.py` — the centerpiece

`run_wizard(target, *, skip_prompts, project_name, model_id, source_ids, force)` drives the
`init` flow and generates the project. Key pieces:

- `MODELS` — the AI-model menu (`ModelChoice`: provider, model id, runtime). Claude models use the `claude-code` runtime; others are `api` (provider adapters, Phase 5).
- `SOURCES` — the data-inflow menu (`SourceChoice`: kind + `env_keys` + `default_config()` for `sources/<id>.yaml`).
- `_build_house()` — the progress-bar phase. Each step is a real generator: dirs, `litmus.yaml`, `sources/*.yaml`, the transform/dashboard/test starters, the agent team (`install_agent_team`), `.litmus/context.md` (the brief the agents read), `.env.example`, `.litmus/state.json`, and the sample load.
- `reconfigure(target)` — backs `litmus configure`.

The generated files are **parameterized by the user's source selection** — a project that picks Postgres + Stripe gets source configs, an agent context, and an `.env.example` that reference exactly those.

### `litmus/cli.py` — the command surface (dbt-style, agent-fronted)

`init`, `configure`, `run`, `test`, `dashboard`, `add`, `ingest`, `transform`, `demo`, `doctor`, `connect`, `ask`, `agent`. Bare `litmus` (no subcommand) launches the TUI when stdin is a TTY, else prints help. `ask`/`agent` and the REPL all route to the team via `_dispatch_to_team()` → the Claude Code CLI (`claude --print`), grounding it with `DATA_ENGINEERING_SCOPE` + `.litmus/context.md`. Heavy imports stay **inside** each command so `litmus --help` is fast — preserve that.

`litmus test` runs every `tests/*.sql` against the warehouse; a test passes when it returns **zero rows** and the command exits 1 if any test returns rows.

### Agent runtime

The interactive chat is **Python** — no TypeScript. It shells out to the Claude Code CLI today. The roadmap (Phase 5, see `REFACTOR_VISION.md`) is an `AgentRuntime` interface with a Claude Agent SDK in-process path and adapter stubs for OpenAI / Google / local, resolved from the model the user picked in `init`.

## Tests

`tests/test_cli.py` is the suite — it drives the wizard and commands through Click's `CliRunner` in an isolated filesystem. Prefer end-to-end CLI tests over mocking. `tests/conftest.py` holds shared fixtures.

## Conventions

- `ruff` (`target-version = "py310"`, `line-length = 100`, rules `E,F,I,N,W,UP`) + `mypy litmus/`. `from __future__ import annotations` throughout.
- Credentials via env vars only (referenced as `${VAR}` in `sources/*.yaml`); `.env` is gitignored.
- Templates ship in the wheel via `[tool.setuptools.package-data]` — when adding an agent, skill, or template file, add its glob there.
- The wizard and the TUI share one scaffold path (`litmus.scaffold.install_agent_team`) — keep them in sync; don't fork it.
