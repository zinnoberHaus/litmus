"""Tests for litmus.cli — Click CLI commands."""

from __future__ import annotations

from pathlib import Path
from textwrap import dedent

import pytest
from click.testing import CliRunner

from litmus.cli import main

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_VALID_METRIC = dedent("""\
    Metric: CLI Test Revenue
    Description: Revenue metric for CLI testing
    Owner: test-team
    Tags: test

    Source: orders

    Given all records from orders table
      And status is "completed"

    When we calculate
      Then sum the amount column

    The result is "CLI Test Revenue"

    Trust:
      Freshness must be less than 24 hours
      Null rate on amount must be less than 5%
      Row count must not drop more than 25% day over day
      Value must be between 0 and 1,000,000
""")


@pytest.fixture()
def runner() -> CliRunner:
    return CliRunner()


@pytest.fixture()
def metric_file(tmp_path: Path) -> Path:
    """Write a valid .metric file and return its path."""
    p = tmp_path / "test_revenue.metric"
    p.write_text(_VALID_METRIC, encoding="utf-8")
    return p


@pytest.fixture()
def litmus_config(tmp_path: Path) -> Path:
    """Write a minimal litmus.yml that uses in-memory DuckDB."""
    cfg = tmp_path / "litmus.yml"
    cfg.write_text(dedent("""\
        version: 1
        metrics_dir: metrics/
        warehouse:
          type: duckdb
          database: ":memory:"
        reporting:
          format: console
    """))
    return cfg


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
# Parse command
# ---------------------------------------------------------------------------


class TestParseCommand:
    def test_parse_valid_file(self, runner: CliRunner, metric_file: Path):
        result = runner.invoke(main, ["parse", str(metric_file)])
        assert result.exit_code == 0
        assert "CLI Test Revenue" in result.output
        assert "sources" in result.output.lower() or "orders" in result.output

    def test_parse_shows_trust_rules(self, runner: CliRunner, metric_file: Path):
        result = runner.invoke(main, ["parse", str(metric_file)])
        assert result.exit_code == 0
        assert "freshness" in result.output.lower()

    def test_parse_nonexistent_file(self, runner: CliRunner):
        result = runner.invoke(main, ["parse", "/nonexistent/path.metric"])
        assert result.exit_code != 0


# ---------------------------------------------------------------------------
# Init command
# ---------------------------------------------------------------------------


class TestInitCommand:
    def test_init_creates_files(self, runner: CliRunner, tmp_path: Path):
        with runner.isolated_filesystem(temp_dir=tmp_path):
            result = runner.invoke(main, ["init"])
            assert result.exit_code == 0
            assert Path("litmus.yml").exists()
            assert Path("metrics").is_dir()
            assert Path("metrics/example.metric").exists()

    def test_init_idempotent(self, runner: CliRunner, tmp_path: Path):
        with runner.isolated_filesystem(temp_dir=tmp_path):
            # Run init twice
            runner.invoke(main, ["init"])
            result = runner.invoke(main, ["init"])
            assert result.exit_code == 0
            # Files should still exist
            assert Path("litmus.yml").exists()
            assert Path("metrics/example.metric").exists()


# ---------------------------------------------------------------------------
# Explain command
# ---------------------------------------------------------------------------


class TestExplainCommand:
    def test_explain_produces_output(self, runner: CliRunner, metric_file: Path):
        result = runner.invoke(main, ["explain", str(metric_file)])
        assert result.exit_code == 0
        assert "CLI Test Revenue" in result.output

    def test_explain_includes_trust_description(self, runner: CliRunner, metric_file: Path):
        result = runner.invoke(main, ["explain", str(metric_file)])
        assert result.exit_code == 0
        # The plain_english generator mentions trust checks
        output = result.output.lower()
        assert (
            "hours" in output
            or "trust" in output
            or "check" in output
        )


# ---------------------------------------------------------------------------
# Check command
# ---------------------------------------------------------------------------


class TestCheckCommand:
    def test_check_with_duckdb(
        self, runner: CliRunner, metric_file: Path, litmus_config: Path
    ):
        """Run check against an in-memory DuckDB.

        The DuckDB will have no orders table, so trust checks will
        produce errors, but the CLI should still run to completion and
        render output.
        """
        result = runner.invoke(
            main, ["check", str(metric_file), "-c", str(litmus_config)]
        )
        # The check command exits 1 when checks fail/error, which is expected
        # here since there is no actual table. The key assertion is that it
        # does not crash with an unhandled exception.
        assert result.exit_code in (0, 1)
        # Should produce some output (either results or error info)
        assert len(result.output) > 0

    def test_check_nonexistent_path(self, runner: CliRunner):
        result = runner.invoke(main, ["check", "/nonexistent/path.metric"])
        assert result.exit_code != 0

    def test_check_directory_no_metrics(self, runner: CliRunner, tmp_path: Path):
        empty_dir = tmp_path / "empty_metrics"
        empty_dir.mkdir()
        result = runner.invoke(main, ["check", str(empty_dir)])
        assert result.exit_code != 0
        assert "no .metric files" in result.output.lower() or "not found" in result.output.lower()
