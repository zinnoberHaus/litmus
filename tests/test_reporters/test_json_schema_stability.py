"""Enforce the v1 JSON contract — fails loudly when the reporter drifts from schemas/v1/."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from litmus.checks.runner import CheckResult, CheckStatus, CheckSuite
from litmus.reporters.json_reporter import SCHEMA_VERSION, generate_json_report
from litmus.spec.metric_spec import FreshnessRule, MetricSpec, NullRule, TrustSpec

SCHEMA_PATH = Path(__file__).resolve().parents[2] / "schemas" / "v1" / "check-suite.schema.json"


def _sample_report() -> dict:
    spec = MetricSpec(
        name="Test Revenue",
        description="desc",
        owner="data-team",
        tags=["finance"],
        sources=["orders"],
        trust=TrustSpec(
            freshness=FreshnessRule(max_hours=24.0),
            null_rules=[NullRule(column="amount", max_percentage=5.0)],
        ),
    )
    suite = CheckSuite(
        metric_name="Test Revenue",
        results=[
            CheckResult(
                name="Freshness",
                status=CheckStatus.PASSED,
                message="Freshness: 1h (< 24h)",
                actual_value=1.0,
                threshold=24.0,
            ),
            CheckResult(
                name="Null rate on amount",
                status=CheckStatus.FAILED,
                message="12.5% > 5.0%",
                actual_value=12.5,
                threshold=5.0,
            ),
        ],
    )
    raw = generate_json_report([(spec, suite)])
    return json.loads(raw)


def test_schema_file_exists():
    assert SCHEMA_PATH.is_file(), f"JSON schema missing at {SCHEMA_PATH}"


def test_report_declares_schema_version():
    report = _sample_report()
    assert report["schema_version"] == "v1"
    assert SCHEMA_VERSION == "v1"


def test_report_has_required_top_level_fields():
    report = _sample_report()
    for field in ("litmus_version", "schema_version", "generated_at", "metrics", "summary"):
        assert field in report, f"missing required top-level field: {field}"


def test_metric_has_required_fields():
    report = _sample_report()
    metric = report["metrics"][0]
    for field in ("name", "trust_score", "trust_total", "checks"):
        assert field in metric, f"metric missing required field: {field}"


def test_check_has_required_fields_and_valid_status():
    report = _sample_report()
    valid_statuses = {"passed", "warning", "failed", "error"}
    for check in report["metrics"][0]["checks"]:
        for field in ("name", "status", "message"):
            assert field in check, f"check missing required field: {field}"
        assert check["status"] in valid_statuses


def test_summary_counts_are_non_negative_integers():
    report = _sample_report()
    for key in ("total", "healthy", "warning", "failing"):
        val = report["summary"][key]
        assert isinstance(val, int)
        assert val >= 0


def test_generate_with_explicit_v1_works():
    spec = MetricSpec(name="x")
    suite = CheckSuite(metric_name="x")
    raw = generate_json_report([(spec, suite)], schema_version="v1")
    assert json.loads(raw)["schema_version"] == "v1"


def test_unknown_schema_version_raises():
    spec = MetricSpec(name="x")
    suite = CheckSuite(metric_name="x")
    with pytest.raises(ValueError, match="Unsupported schema_version"):
        generate_json_report([(spec, suite)], schema_version="v999")


def test_schema_file_is_valid_json_schema():
    """Basic sanity — the schema file itself parses and has expected top-level keys."""
    with open(SCHEMA_PATH) as f:
        schema = json.load(f)
    assert schema["$schema"].startswith("https://json-schema.org/")
    assert schema["title"] == "Litmus check report (v1)"
    assert "metrics" in schema["properties"]
    assert "summary" in schema["properties"]


def test_report_validates_against_schema_if_jsonschema_available():
    """If jsonschema is installed, fully validate; otherwise skip gracefully."""
    jsonschema = pytest.importorskip("jsonschema")
    with open(SCHEMA_PATH) as f:
        schema = json.load(f)
    report = _sample_report()
    jsonschema.validate(instance=report, schema=schema)
