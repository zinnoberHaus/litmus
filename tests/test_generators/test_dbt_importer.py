"""Tests for litmus.generators.dbt_importer — dbt manifest import."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from litmus.generators.dbt_importer import generate_metric_file, import_dbt_manifest

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

_MANIFEST_WITH_METRICS = {
    "metadata": {"dbt_version": "1.7.0"},
    "metrics": {
        "metric.project.total_revenue": {
            "name": "total_revenue",
            "label": "Total Revenue",
            "description": "Sum of all completed order amounts",
            "type": "sum",
            "expression": "amount",
            "tags": ["finance", "revenue"],
            "depends_on": {
                "nodes": ["model.project.orders"]
            },
            "filters": [
                {"field": "status", "operator": "=", "value": "completed"}
            ],
            "meta": {"owner": "data-team"},
        }
    },
    "nodes": {},
}

_MANIFEST_WITH_MODELS = {
    "metadata": {"dbt_version": "1.7.0"},
    "metrics": {},
    "nodes": {
        "model.project.orders": {
            "resource_type": "model",
            "name": "orders",
            "description": "Clean orders table",
            "tags": ["core"],
            "columns": {
                "order_id": {
                    "description": "Primary key",
                    "tests": ["not_null", "unique"],
                },
                "amount": {
                    "description": "Order total",
                    "tests": [],
                },
            },
            "meta": {"owner": "analytics"},
        }
    },
}


@pytest.fixture()
def manifest_with_metrics(tmp_path: Path) -> Path:
    p = tmp_path / "manifest.json"
    p.write_text(json.dumps(_MANIFEST_WITH_METRICS))
    return p


@pytest.fixture()
def manifest_with_models(tmp_path: Path) -> Path:
    p = tmp_path / "manifest.json"
    p.write_text(json.dumps(_MANIFEST_WITH_MODELS))
    return p


@pytest.fixture()
def empty_manifest(tmp_path: Path) -> Path:
    p = tmp_path / "manifest.json"
    p.write_text(json.dumps({"metadata": {}, "metrics": {}, "nodes": {}}))
    return p


# ---------------------------------------------------------------------------
# import_dbt_manifest tests
# ---------------------------------------------------------------------------


class TestImportDbtMetrics:
    """Import from the dbt metrics section."""

    def test_extracts_one_metric(self, manifest_with_metrics: Path):
        specs = import_dbt_manifest(manifest_with_metrics)
        assert len(specs) == 1

    def test_metric_name(self, manifest_with_metrics: Path):
        specs = import_dbt_manifest(manifest_with_metrics)
        assert specs[0].name == "Total Revenue"

    def test_metric_description(self, manifest_with_metrics: Path):
        specs = import_dbt_manifest(manifest_with_metrics)
        assert specs[0].description == "Sum of all completed order amounts"

    def test_metric_sources(self, manifest_with_metrics: Path):
        specs = import_dbt_manifest(manifest_with_metrics)
        assert "orders" in specs[0].sources

    def test_metric_tags(self, manifest_with_metrics: Path):
        specs = import_dbt_manifest(manifest_with_metrics)
        assert "finance" in specs[0].tags

    def test_metric_owner(self, manifest_with_metrics: Path):
        specs = import_dbt_manifest(manifest_with_metrics)
        assert specs[0].owner == "data-team"

    def test_metric_conditions(self, manifest_with_metrics: Path):
        specs = import_dbt_manifest(manifest_with_metrics)
        assert len(specs[0].conditions) >= 1
        assert any("status" in c for c in specs[0].conditions)

    def test_metric_calculations(self, manifest_with_metrics: Path):
        specs = import_dbt_manifest(manifest_with_metrics)
        assert len(specs[0].calculations) >= 1
        assert any("sum" in c.lower() for c in specs[0].calculations)

    def test_default_trust_rules(self, manifest_with_metrics: Path):
        specs = import_dbt_manifest(manifest_with_metrics)
        trust = specs[0].trust
        assert trust is not None
        assert trust.freshness is not None
        assert trust.freshness.max_hours == 24
        assert len(trust.volume_rules) >= 1


class TestImportDbtModels:
    """Fallback to dbt models when no metrics section."""

    def test_extracts_from_models(self, manifest_with_models: Path):
        specs = import_dbt_manifest(manifest_with_models)
        assert len(specs) == 1

    def test_model_name(self, manifest_with_models: Path):
        specs = import_dbt_manifest(manifest_with_models)
        assert specs[0].name == "Orders"

    def test_not_null_creates_null_rule(self, manifest_with_models: Path):
        specs = import_dbt_manifest(manifest_with_models)
        trust = specs[0].trust
        assert trust is not None
        null_columns = [r.column for r in trust.null_rules]
        assert "order_id" in null_columns


class TestImportEmptyManifest:
    """Empty manifest returns empty list."""

    def test_returns_empty(self, empty_manifest: Path):
        specs = import_dbt_manifest(empty_manifest)
        assert specs == []


# ---------------------------------------------------------------------------
# generate_metric_file tests
# ---------------------------------------------------------------------------


class TestGenerateMetricFile:
    """Test that generate_metric_file produces valid .metric format."""

    def test_output_contains_metric_header(self, manifest_with_metrics: Path):
        specs = import_dbt_manifest(manifest_with_metrics)
        output = generate_metric_file(specs[0])
        assert output.startswith("Metric: Total Revenue")

    def test_output_contains_source(self, manifest_with_metrics: Path):
        specs = import_dbt_manifest(manifest_with_metrics)
        output = generate_metric_file(specs[0])
        assert "Source: orders" in output

    def test_output_contains_trust_block(self, manifest_with_metrics: Path):
        specs = import_dbt_manifest(manifest_with_metrics)
        output = generate_metric_file(specs[0])
        assert "Trust:" in output
        assert "Freshness" in output

    def test_roundtrip_parseable(self, manifest_with_metrics: Path):
        """The generated .metric text should be parseable back into a MetricSpec."""
        from litmus.parser.parser import parse_metric_string

        specs = import_dbt_manifest(manifest_with_metrics)
        output = generate_metric_file(specs[0])
        reparsed = parse_metric_string(output)
        assert reparsed.name == specs[0].name

    def test_includes_given_conditions(self, manifest_with_metrics: Path):
        specs = import_dbt_manifest(manifest_with_metrics)
        output = generate_metric_file(specs[0])
        assert "Given" in output

    def test_includes_when_block(self, manifest_with_metrics: Path):
        specs = import_dbt_manifest(manifest_with_metrics)
        output = generate_metric_file(specs[0])
        assert "When we calculate" in output

    def test_includes_result(self, manifest_with_metrics: Path):
        specs = import_dbt_manifest(manifest_with_metrics)
        output = generate_metric_file(specs[0])
        assert 'The result is "Total Revenue"' in output
