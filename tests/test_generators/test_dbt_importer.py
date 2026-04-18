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


# ---------------------------------------------------------------------------
# build_lineage tests
# ---------------------------------------------------------------------------


_LINEAGE_MANIFEST = {
    "metrics": {
        "metric.project.total_revenue": {
            "name": "total_revenue",
            "label": "Total Revenue",
            "description": "",
        }
    },
    "nodes": {
        "model.project.fct_orders": {
            "resource_type": "model",
            "name": "fct_orders",
        },
        "model.project.stg_orders": {
            "resource_type": "model",
            "name": "stg_orders",
        },
        "model.project.stg_payments": {
            "resource_type": "model",
            "name": "stg_payments",
        },
    },
    "sources": {
        "source.project.raw.orders": {
            "name": "orders",
            "identifier": "orders",
        },
        "source.project.raw.payments": {
            "name": "payments",
            "identifier": "payments",
        },
    },
    # parent_map: child -> [parents]
    "parent_map": {
        "metric.project.total_revenue": ["model.project.fct_orders"],
        "model.project.fct_orders": [
            "model.project.stg_orders",
            "model.project.stg_payments",
        ],
        "model.project.stg_orders": ["source.project.raw.orders"],
        "model.project.stg_payments": ["source.project.raw.payments"],
        "source.project.raw.orders": [],
        "source.project.raw.payments": [],
    },
}


class TestBuildLineage:
    def test_walks_up_to_three_hops(self):
        from litmus.generators.dbt_importer import build_lineage

        lineage = build_lineage(_LINEAGE_MANIFEST, "total_revenue")
        labels = {n.label for n in lineage.nodes}
        # 3 hops up: metric → fct_orders → stg_* → source.raw.*
        assert "Total Revenue" in labels
        assert "fct_orders" in labels
        assert "stg_orders" in labels
        assert "stg_payments" in labels
        assert "orders" in labels
        assert "payments" in labels

    def test_source_nodes_have_source_kind(self):
        from litmus.generators.dbt_importer import build_lineage

        lineage = build_lineage(_LINEAGE_MANIFEST, "total_revenue")
        kinds = {n.label: n.kind for n in lineage.nodes}
        assert kinds["orders"] == "source"
        assert kinds["payments"] == "source"

    def test_intermediate_nodes_have_model_kind(self):
        from litmus.generators.dbt_importer import build_lineage

        lineage = build_lineage(_LINEAGE_MANIFEST, "total_revenue")
        kinds = {n.label: n.kind for n in lineage.nodes}
        assert kinds["fct_orders"] == "model"
        assert kinds["stg_orders"] == "model"

    def test_metric_terminal_node_always_present(self):
        from litmus.generators.dbt_importer import build_lineage

        lineage = build_lineage(_LINEAGE_MANIFEST, "total_revenue")
        metric_nodes = [n for n in lineage.nodes if n.kind == "metric"]
        assert len(metric_nodes) == 1
        assert metric_nodes[0].label == "Total Revenue"

    def test_edges_flow_source_to_metric(self):
        from litmus.generators.dbt_importer import build_lineage

        lineage = build_lineage(_LINEAGE_MANIFEST, "total_revenue")
        node_ids = {n.id for n in lineage.nodes}
        # Every edge must reference nodes we actually returned.
        for edge in lineage.edges:
            assert edge.from_id in node_ids
            assert edge.to_id in node_ids

    def test_unknown_metric_returns_degenerate_graph(self):
        from litmus.generators.dbt_importer import build_lineage

        lineage = build_lineage(_LINEAGE_MANIFEST, "not_a_real_metric")
        # Metric we can't resolve still gets a terminal node so the UI
        # doesn't see an empty graph.
        assert len(lineage.nodes) == 1
        assert lineage.nodes[0].kind == "metric"
        assert lineage.edges == []

    def test_depth_cap_truncates_deep_chains(self):
        from litmus.generators.dbt_importer import build_lineage

        # Construct a 5-hop chain; we should see at most 3 hops from the start.
        manifest = {
            "metrics": {},
            "nodes": {
                "model.p.a": {"resource_type": "model", "name": "a"},
                "model.p.b": {"resource_type": "model", "name": "b"},
                "model.p.c": {"resource_type": "model", "name": "c"},
                "model.p.d": {"resource_type": "model", "name": "d"},
                "model.p.e": {"resource_type": "model", "name": "e"},
            },
            "sources": {},
            "parent_map": {
                "model.p.a": ["model.p.b"],
                "model.p.b": ["model.p.c"],
                "model.p.c": ["model.p.d"],
                "model.p.d": ["model.p.e"],
                "model.p.e": [],
            },
        }
        lineage = build_lineage(manifest, "a")
        labels = {n.label for n in lineage.nodes}
        # Start is "a" (model), plus metric terminal, plus 3 hops up:
        # a, b, c, d. "e" is 4 hops up and must be truncated.
        assert "a" in labels
        assert "b" in labels
        assert "c" in labels
        assert "d" in labels
        assert "e" not in labels
