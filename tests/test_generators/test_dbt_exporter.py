"""Tests for litmus.generators.dbt_exporter — .metric → dbt artefacts."""

from __future__ import annotations

import yaml

from litmus.generators.dbt_exporter import (
    DbtExportBundle,
    _slug,
    export_to_dbt,
)
from litmus.parser.parser import parse_metric_string
from litmus.spec.metric_spec import (
    ChangeRule,
    DistributionShiftRule,
    DuplicateRule,
    FreshnessRule,
    MetricSpec,
    NullRule,
    RangeRule,
    SchemaDriftRule,
    TrustSpec,
    VolumeRule,
)

# ---------------------------------------------------------------------------
# Helpers / fixtures
# ---------------------------------------------------------------------------


def _base_spec(**overrides) -> MetricSpec:
    kwargs: dict = dict(
        name="Monthly Revenue",
        description="Sum of net revenue for the calendar month.",
        owner="finance-analytics",
        tags=["revenue", "finance"],
        sources=["invoices"],
        conditions=['status is "completed"'],
        calculations=["sum the net_amount column"],
        result_name="Monthly Revenue",
    )
    kwargs.update(overrides)
    return MetricSpec(**kwargs)


# ---------------------------------------------------------------------------
# Slug tests
# ---------------------------------------------------------------------------


class TestSlug:
    def test_basic(self):
        assert _slug("Monthly Revenue") == "monthly_revenue"

    def test_trims_whitespace(self):
        assert _slug("  Total Orders  ") == "total_orders"

    def test_strips_punctuation(self):
        assert _slug("Q4 Revenue (USD)") == "q4_revenue_usd"

    def test_hyphens_become_underscores(self):
        assert _slug("active-users") == "active_users"


# ---------------------------------------------------------------------------
# No-trust fallback
# ---------------------------------------------------------------------------


class TestEmptyTrust:
    def test_returns_bundle_without_trust_block(self):
        spec = _base_spec()
        bundle = export_to_dbt(spec)
        assert isinstance(bundle, DbtExportBundle)
        assert bundle.metric_slug == "monthly_revenue"

    def test_model_yaml_still_valid(self):
        spec = _base_spec()
        bundle = export_to_dbt(spec)
        doc = yaml.safe_load(bundle.model_yaml)
        assert doc["version"] == 2
        assert doc["models"][0]["name"] == "monthly_revenue"
        assert doc["models"][0]["config"]["tags"] == ["litmus"]

    def test_singular_test_is_a_noop_select(self):
        spec = _base_spec()
        bundle = export_to_dbt(spec)
        assert "select 1 where false" in bundle.singular_test_sql.lower()


# ---------------------------------------------------------------------------
# Clean model-YAML mappings: not_null / unique / accepted_range
# ---------------------------------------------------------------------------


class TestCleanModelYamlMappings:
    def test_zero_null_rate_becomes_not_null(self):
        spec = _base_spec(trust=TrustSpec(
            null_rules=[NullRule(column="currency", max_percentage=0)],
        ))
        bundle = export_to_dbt(spec)
        doc = yaml.safe_load(bundle.model_yaml)
        cols = {c["name"]: c for c in doc["models"][0]["columns"]}
        assert "not_null" in cols["currency"]["tests"]

    def test_zero_duplicate_rate_becomes_unique(self):
        spec = _base_spec(trust=TrustSpec(
            duplicate_rules=[DuplicateRule(column="invoice_id", max_percentage=0)],
        ))
        bundle = export_to_dbt(spec)
        doc = yaml.safe_load(bundle.model_yaml)
        cols = {c["name"]: c for c in doc["models"][0]["columns"]}
        assert "unique" in cols["invoice_id"]["tests"]

    def test_range_becomes_accepted_range(self):
        spec = _base_spec(trust=TrustSpec(
            range_rules=[RangeRule(min_value=10000.0, max_value=5_000_000.0)],
        ))
        bundle = export_to_dbt(spec)
        doc = yaml.safe_load(bundle.model_yaml)
        cols = {c["name"]: c for c in doc["models"][0]["columns"]}
        range_test = cols["amount"]["tests"][0]
        assert "dbt_utils.accepted_range" in range_test
        assert range_test["dbt_utils.accepted_range"]["min_value"] == 10000.0
        assert range_test["dbt_utils.accepted_range"]["max_value"] == 5_000_000.0

    def test_column_description_placeholder(self):
        """Never fabricate: emit TODO so humans review."""
        spec = _base_spec(trust=TrustSpec(
            null_rules=[NullRule(column="currency", max_percentage=0)],
        ))
        bundle = export_to_dbt(spec)
        doc = yaml.safe_load(bundle.model_yaml)
        col = doc["models"][0]["columns"][0]
        assert col["description"] == "# TODO: describe"


# ---------------------------------------------------------------------------
# Singular-test mappings: non-zero thresholds + freshness
# ---------------------------------------------------------------------------


class TestSingularSqlMappings:
    def test_freshness_emits_having_clause(self):
        spec = _base_spec(trust=TrustSpec(
            freshness=FreshnessRule(max_hours=6),
        ))
        bundle = export_to_dbt(spec)
        sql = bundle.singular_test_sql
        assert "freshness" in sql
        assert "having" in sql.lower()
        assert "6" in sql

    def test_non_zero_null_rate_in_singular(self):
        spec = _base_spec(trust=TrustSpec(
            null_rules=[NullRule(column="net_amount", max_percentage=1)],
        ))
        bundle = export_to_dbt(spec)
        sql = bundle.singular_test_sql
        assert "null_rate_net_amount" in sql
        doc = yaml.safe_load(bundle.model_yaml)
        # Non-zero nulls shouldn't emit not_null in the model YAML.
        assert doc["models"][0].get("columns") in (None, [])

    def test_non_zero_duplicate_in_singular(self):
        spec = _base_spec(trust=TrustSpec(
            duplicate_rules=[DuplicateRule(column="order_id", max_percentage=0.5)],
        ))
        bundle = export_to_dbt(spec)
        sql = bundle.singular_test_sql
        assert "duplicate_rate_order_id" in sql
        assert "0.5" in sql

    def test_ref_points_to_primary_source(self):
        spec = _base_spec(sources=["invoices"], trust=TrustSpec(
            freshness=FreshnessRule(max_hours=6),
        ))
        bundle = export_to_dbt(spec)
        assert "{{ ref('invoices') }}" in bundle.singular_test_sql


# ---------------------------------------------------------------------------
# Stateful rules → TODO markers
# ---------------------------------------------------------------------------


class TestStatefulRulesFlaggedAsTodo:
    def test_volume_rule_emits_todo(self):
        spec = _base_spec(trust=TrustSpec(
            volume_rules=[VolumeRule(table=None, max_drop_percentage=15, period="day")],
        ))
        bundle = export_to_dbt(spec)
        assert "TODO" in bundle.singular_test_sql
        assert "litmus check" in bundle.singular_test_sql

    def test_change_rule_emits_todo(self):
        spec = _base_spec(trust=TrustSpec(
            change_rules=[ChangeRule(max_change_percentage=40, period="month")],
        ))
        bundle = export_to_dbt(spec)
        assert "TODO" in bundle.singular_test_sql
        todo_entries = [m for m in bundle.mappings if m.dbt_target == "todo"]
        assert any("change" in t.litmus_rule.lower() for t in todo_entries)

    def test_schema_drift_emits_todo(self):
        spec = _base_spec(trust=TrustSpec(
            schema_drift=SchemaDriftRule(),
        ))
        bundle = export_to_dbt(spec)
        assert "Schema drift" in bundle.singular_test_sql
        assert "equal_column_names" in bundle.singular_test_sql

    def test_distribution_shift_emits_todo(self):
        spec = _base_spec(trust=TrustSpec(
            distribution_shift_rules=[
                DistributionShiftRule(
                    column="net_amount",
                    max_change_percentage=25,
                    period="month",
                ),
            ],
        ))
        bundle = export_to_dbt(spec)
        assert "Distribution shift" in bundle.singular_test_sql
        assert "mean(net_amount)" in bundle.singular_test_sql.lower()


# ---------------------------------------------------------------------------
# Mapping doc (round-trip traceability)
# ---------------------------------------------------------------------------


class TestMappingDoc:
    def test_mapping_mentions_every_rule(self):
        spec = _base_spec(trust=TrustSpec(
            freshness=FreshnessRule(max_hours=6),
            null_rules=[
                NullRule(column="net_amount", max_percentage=1),
                NullRule(column="currency", max_percentage=0),
            ],
            duplicate_rules=[DuplicateRule(column="invoice_id", max_percentage=0)],
            range_rules=[RangeRule(min_value=10000.0, max_value=5_000_000.0)],
            schema_drift=SchemaDriftRule(),
        ))
        bundle = export_to_dbt(spec)
        md = bundle.mapping_markdown
        assert "Monthly Revenue" in md
        assert "Freshness" in md
        assert "net_amount" in md
        assert "invoice_id" in md
        assert "accepted_range" in md or "between" in md.lower()
        assert "Schema must not drift" in md

    def test_todo_section_present_when_stateful_rules_exist(self):
        spec = _base_spec(trust=TrustSpec(
            schema_drift=SchemaDriftRule(),
        ))
        bundle = export_to_dbt(spec)
        assert "Rules that still need `litmus check`" in bundle.mapping_markdown

    def test_no_todo_section_when_all_rules_clean(self):
        spec = _base_spec(trust=TrustSpec(
            null_rules=[NullRule(column="currency", max_percentage=0)],
            range_rules=[RangeRule(min_value=0, max_value=100)],
        ))
        bundle = export_to_dbt(spec)
        assert "Rules that still need `litmus check`" not in bundle.mapping_markdown


# ---------------------------------------------------------------------------
# End-to-end: the bundled revenue.metric example
# ---------------------------------------------------------------------------


_REVENUE_METRIC = """\
Metric: Monthly Revenue
Description: Total revenue for the current calendar month.
Owner: finance-analytics
Tags: revenue, finance

Source: invoices

Given the invoice has been finalized

When we calculate
  Then sum the net_amount column

The result is "Monthly Revenue"

Trust:
  Freshness must be less than 6 hours
  Null rate on net_amount must be less than 1%
  Null rate on currency must be less than 0%
  Row count must not drop more than 15% day over day
  Value must be between 10000 and 5000000
  Value must not change more than 40% month over month
  Duplicate rate on invoice_id must be 0%
  Schema must not drift
  Mean of net_amount must not change more than 25% month over month
"""


class TestRevenueMetricRoundTrip:
    def test_parses_and_exports(self):
        spec = parse_metric_string(_REVENUE_METRIC)
        bundle = export_to_dbt(spec)

        # Model YAML is syntactically valid YAML.
        doc = yaml.safe_load(bundle.model_yaml)
        model = doc["models"][0]
        assert model["name"] == "monthly_revenue"
        assert model["config"]["tags"] == ["litmus"]

        # zero-null-rate + zero-dup-rate surface as not_null / unique.
        cols_by_name = {c["name"]: c for c in model.get("columns", [])}
        assert "not_null" in cols_by_name["currency"]["tests"]
        assert "unique" in cols_by_name["invoice_id"]["tests"]

        # accepted_range lands on the default `amount` column.
        amount_tests = cols_by_name["amount"]["tests"]
        assert any("dbt_utils.accepted_range" in t for t in amount_tests)

    def test_singular_test_includes_all_non_clean_rules(self):
        spec = parse_metric_string(_REVENUE_METRIC)
        bundle = export_to_dbt(spec)
        sql = bundle.singular_test_sql
        assert "freshness" in sql
        assert "null_rate_net_amount" in sql  # 1% threshold, not zero
        assert "Volume drop" in sql
        assert "Value change" in sql
        assert "Distribution shift" in sql
        assert "Schema drift" in sql

    def test_mapping_doc_has_every_rule(self):
        spec = parse_metric_string(_REVENUE_METRIC)
        bundle = export_to_dbt(spec)
        md = bundle.mapping_markdown
        # One table row per distinct rule.
        table_rows = [ln for ln in md.splitlines() if ln.startswith("| ")]
        # Header row + one row per rule (9 rules in _REVENUE_METRIC). Separator
        # line starts with "|-" so it's excluded.
        assert len(table_rows) >= 10


# ---------------------------------------------------------------------------
# Filename conventions
# ---------------------------------------------------------------------------


class TestFilenames:
    def test_model_filename(self):
        bundle = export_to_dbt(_base_spec())
        assert bundle.model_filename == "monthly_revenue.yml"

    def test_test_filename(self):
        bundle = export_to_dbt(_base_spec())
        assert bundle.test_filename == "monthly_revenue_trust.sql"

    def test_mapping_filename(self):
        bundle = export_to_dbt(_base_spec())
        assert bundle.mapping_filename == "mapping_monthly_revenue.md"
