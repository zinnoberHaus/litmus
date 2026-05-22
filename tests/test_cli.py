"""Tests for litmus.cli — Click CLI commands."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from click.testing import CliRunner

from litmus.cli import main


@pytest.fixture()
def runner() -> CliRunner:
    return CliRunner()


# ---------------------------------------------------------------------------
# Version
# ---------------------------------------------------------------------------


class TestVersion:
    def test_version_flag(self, runner: CliRunner):
        result = runner.invoke(main, ["--version"])
        assert result.exit_code == 0
        assert "litmus" in result.output.lower()
        assert "0." in result.output  # version starts with 0.x


# ---------------------------------------------------------------------------
# Init command — the setup wizard
# ---------------------------------------------------------------------------


class TestInitCommand:
    """`litmus init` is the setup wizard — it builds the 'Litmus house':
    a model choice, the chosen data sources, the transform/dashboard/test
    framework, and the agent team. No trust-engine artifacts.
    """

    def test_init_cwd_mode_builds_the_house(self, runner: CliRunner, tmp_path: Path):
        with runner.isolated_filesystem(temp_dir=tmp_path):
            result = runner.invoke(main, ["init", ".", "--yes", "--source", "warehouse"])
            assert result.exit_code == 0, result.output
            # Project config + framework folders.
            assert Path("litmus.yaml").exists()
            assert Path("sources/warehouse.yaml").exists()
            assert Path("transforms").is_dir()
            assert Path("dashboards").is_dir()
            assert Path("tests").is_dir()
            assert Path(".env.example").exists()
            # Agent team.
            assert Path(".claude/agents").is_dir()
            assert any(Path(".claude/agents").glob("*.md"))
            assert Path(".mcp.json").exists()
            assert Path("AGENTS.md").exists()
            assert Path(".litmus/state.json").exists()
            assert Path(".litmus/context.md").exists()
            # No trust-engine artifacts.
            assert not Path("metrics").exists()
            assert not Path("litmus.yml").exists()

    def test_init_idempotent(self, runner: CliRunner, tmp_path: Path):
        """Re-running is safe — existing files are kept, no error."""
        with runner.isolated_filesystem(temp_dir=tmp_path):
            runner.invoke(main, ["init", ".", "--yes", "--source", "warehouse"])
            result = runner.invoke(main, ["init", ".", "--yes", "--source", "warehouse"])
            assert result.exit_code == 0, result.output
            assert Path("litmus.yaml").exists()

    def test_init_with_project_name(self, runner: CliRunner, tmp_path: Path):
        """`litmus init <name>` builds into a subdirectory, nothing leaks to cwd."""
        with runner.isolated_filesystem(temp_dir=tmp_path):
            result = runner.invoke(main, ["init", "myproj", "--yes", "--source", "warehouse"])
            assert result.exit_code == 0, result.output
            assert Path("myproj/litmus.yaml").exists()
            assert Path("myproj/.claude/agents").is_dir()
            assert Path("myproj/.litmus/state.json").exists()
            assert not Path("litmus.yaml").exists()
            assert not Path(".claude").exists()

    def test_init_prompts_for_model_and_sources(self, runner: CliRunner, tmp_path: Path):
        """Interactive: name → model number → source numbers."""
        with runner.isolated_filesystem(temp_dir=tmp_path):
            # name=my-biz, model #1 (Claude Opus), sources "3" (Postgres).
            result = runner.invoke(main, ["init"], input="my-biz\n1\n3\n")
            assert result.exit_code == 0, result.output
            assert "Pick an AI model" in result.output
            assert "Choose your data inflow" in result.output
            cfg = Path("litmus.yaml").read_text()
            assert "claude-opus-4-7" in cfg
            assert "postgres" in cfg
            assert Path("sources/postgres.yaml").exists()

    def test_init_refuses_nonempty_directory(self, runner: CliRunner, tmp_path: Path):
        with runner.isolated_filesystem(temp_dir=tmp_path):
            Path("myproj").mkdir()
            (Path("myproj") / "existing.txt").write_text("hi")
            result = runner.invoke(main, ["init", "myproj", "--yes"])
            assert result.exit_code != 0
            assert "already exists" in result.output

    def test_init_model_and_source_flags(self, runner: CliRunner, tmp_path: Path):
        """Flags pre-fill the wizard; multiple --source values are honored."""
        with runner.isolated_filesystem(temp_dir=tmp_path):
            result = runner.invoke(
                main,
                ["init", ".", "--yes", "--model", "claude-opus",
                 "--source", "postgres", "--source", "stripe"],
            )
            assert result.exit_code == 0, result.output
            cfg = Path("litmus.yaml").read_text()
            assert "claude-opus-4-7" in cfg
            assert Path("sources/postgres.yaml").exists()
            assert Path("sources/stripe.yaml").exists()
            env = Path(".env.example").read_text()
            assert "PGHOST" in env
            assert "STRIPE_API_KEY" in env

    def test_init_sample_loads_warehouse(self, runner: CliRunner, tmp_path: Path):
        """The sample source copies CSVs and loads DuckDB tables."""
        import duckdb

        with runner.isolated_filesystem(temp_dir=tmp_path):
            result = runner.invoke(main, ["init", ".", "--yes", "--source", "sample"])
            assert result.exit_code == 0, result.output
            assert Path("data/raw/transactions.csv").exists()
            con = duckdb.connect("data/warehouse.duckdb", read_only=True)
            tables = {
                r[0]
                for r in con.execute(
                    "SELECT table_name FROM information_schema.tables "
                    "WHERE table_schema = 'main'"
                ).fetchall()
            }
            assert "transactions" in tables

    def test_init_state_marks_initialized(self, runner: CliRunner, tmp_path: Path):
        with runner.isolated_filesystem(temp_dir=tmp_path):
            runner.invoke(main, ["init", ".", "--yes", "--source", "warehouse"])
            state = json.loads(Path(".litmus/state.json").read_text())
            assert state["initialized"] is True
            assert state["model"]["provider"] == "anthropic"
            assert "warehouse" in state["sources"]


# ---------------------------------------------------------------------------
# Test command — runs tests/*.sql
# ---------------------------------------------------------------------------


class TestTestCommand:
    def test_test_runs_sql_checks(self, runner: CliRunner, tmp_path: Path):
        with runner.isolated_filesystem(temp_dir=tmp_path):
            runner.invoke(main, ["init", ".", "--yes", "--source", "sample"])
            # The sample loads a 'transactions' table; the generated not_empty
            # test should pass against it.
            result = runner.invoke(main, ["test"])
            assert result.exit_code == 0, result.output
            assert "passed" in result.output.lower()

    def test_test_fails_on_problem_rows(self, runner: CliRunner, tmp_path: Path):
        with runner.isolated_filesystem(temp_dir=tmp_path):
            runner.invoke(main, ["init", ".", "--yes", "--source", "sample"])
            # A test that always returns a row must fail the run.
            Path("tests/always_fails.sql").write_text("SELECT 1 AS problem;")
            result = runner.invoke(main, ["test"])
            assert result.exit_code == 1
            assert "failed" in result.output.lower()
