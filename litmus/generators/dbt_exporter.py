"""Export a ``MetricSpec`` into dbt artefacts.

Generates three files per metric:

1. ``models/litmus/<name>.yml``    — a dbt model block with column-level tests for
   every Trust rule that maps cleanly (``not_null``, ``unique``, ``accepted_range``).
2. ``tests/singular/<name>_trust.sql`` — a dbt singular test with SELECTs for the
   rules that do not have a native dbt test (volume drop, freshness threshold, etc).
3. ``.litmus/mapping_<name>.md``   — a round-trip document enumerating how each
   Trust rule was handled, including ``# TODO`` markers for stateful rules
   (``change_rule``, ``schema_drift``, ``distribution_shift``) that need the
   history store at runtime.

The adapter never invents column descriptions — if the `.metric` file doesn't
supply one it emits ``# TODO: describe`` so a human reviews before merging.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Literal

import yaml

from litmus.spec.metric_spec import MetricSpec


@dataclass
class RuleMapping:
    """One entry in the round-trip mapping doc."""

    litmus_rule: str
    dbt_target: Literal["model_yaml", "singular_sql", "todo"]
    note: str


@dataclass
class DbtExportBundle:
    """The three artefacts produced for a single metric."""

    metric_slug: str
    model_yaml: str
    singular_test_sql: str
    mapping_markdown: str
    mappings: list[RuleMapping] = field(default_factory=list)

    @property
    def model_filename(self) -> str:
        return f"{self.metric_slug}.yml"

    @property
    def test_filename(self) -> str:
        return f"{self.metric_slug}_trust.sql"

    @property
    def mapping_filename(self) -> str:
        return f"mapping_{self.metric_slug}.md"


# ───────────────────────── helpers ──────────────────────────


def _slug(name: str) -> str:
    """Convert ``Monthly Revenue`` → ``monthly_revenue``."""
    cleaned = re.sub(r"[^\w\s-]", "", name.strip().lower())
    return re.sub(r"[-\s]+", "_", cleaned)


def _primary_source(spec: MetricSpec) -> str | None:
    return spec.sources[0] if spec.sources else None


def _description_block(spec: MetricSpec) -> str:
    """Multi-line dbt description preserving owner + trust summary."""
    parts: list[str] = []
    if spec.description:
        parts.append(spec.description.strip())
    if spec.owner:
        parts.append(f"**Owner:** {spec.owner}")
    parts.append("_Generated from a Litmus `.metric` file. Do not edit directly._")
    return "\n\n".join(parts)


# ─────────────────── model-YAML builders ────────────────────


def _build_model_yaml(spec: MetricSpec, mappings: list[RuleMapping]) -> str:
    """Return the YAML for ``models/litmus/<name>.yml``.

    Only rules that have a canonical dbt test get surfaced here; everything
    else goes into the singular-test file.
    """
    trust = spec.trust

    columns: dict[str, dict] = {}

    def _col(name: str) -> dict:
        if name not in columns:
            columns[name] = {
                "name": name,
                "description": "# TODO: describe",
                "tests": [],
            }
        return columns[name]

    if trust is not None:
        # not_null → only when max_percentage == 0
        for null_rule in trust.null_rules:
            if null_rule.max_percentage == 0:
                _col(null_rule.column)["tests"].append("not_null")
                mappings.append(RuleMapping(
                    litmus_rule=f"Null rate on {null_rule.column} = 0%",
                    dbt_target="model_yaml",
                    note="Mapped to column-level `not_null` test.",
                ))
            else:
                mappings.append(RuleMapping(
                    litmus_rule=(
                        f"Null rate on {null_rule.column}"
                        f" < {null_rule.max_percentage}%"
                    ),
                    dbt_target="singular_sql",
                    note=(
                        "Non-zero threshold — dbt's built-in `not_null` is "
                        "binary, so this lives in the singular test."
                    ),
                ))

        # unique → only when duplicate_rate == 0%
        for dup_rule in trust.duplicate_rules:
            if dup_rule.max_percentage == 0:
                _col(dup_rule.column)["tests"].append("unique")
                mappings.append(RuleMapping(
                    litmus_rule=f"Duplicate rate on {dup_rule.column} = 0%",
                    dbt_target="model_yaml",
                    note="Mapped to column-level `unique` test.",
                ))
            else:
                mappings.append(RuleMapping(
                    litmus_rule=(
                        f"Duplicate rate on {dup_rule.column}"
                        f" < {dup_rule.max_percentage}%"
                    ),
                    dbt_target="singular_sql",
                    note="Tolerant threshold — lives in the singular test.",
                ))

        # value_range → dbt_utils.accepted_range on the default value column
        # (same contract as runner.py — default is ``amount``).
        if trust.range_rules:
            range_col = "amount"  # Default value column (per CLAUDE.md conventions).
            for rng in trust.range_rules:
                _col(range_col)["tests"].append({
                    "dbt_utils.accepted_range": {
                        "min_value": rng.min_value,
                        "max_value": rng.max_value,
                    }
                })
                mappings.append(RuleMapping(
                    litmus_rule=(
                        f"Value must be between {rng.min_value:g}"
                        f" and {rng.max_value:g}"
                    ),
                    dbt_target="model_yaml",
                    note=(
                        "Mapped to `dbt_utils.accepted_range`. Requires the "
                        "`dbt_utils` package in packages.yml."
                    ),
                ))

    model = {
        "name": _slug(spec.name),
        "description": _description_block(spec),
        "config": {"tags": ["litmus"]},
    }
    if columns:
        # Strip empty test lists so the YAML stays clean.
        cols_out = []
        for c in columns.values():
            if not c["tests"]:
                c.pop("tests")
            cols_out.append(c)
        model["columns"] = cols_out

    doc = {"version": 2, "models": [model]}

    header = (
        "# Generated by litmus from .metric — do not edit manually.\n"
        f"# Source metric: {spec.name}\n"
    )
    return header + yaml.safe_dump(doc, sort_keys=False, width=100)


# ─────────────────── singular-test builders ─────────────────


def _build_singular_sql(spec: MetricSpec, mappings: list[RuleMapping]) -> str:
    """Emit a singular dbt test SELECTing rows for each rule violation.

    The convention for dbt singular tests is: **failure = at least one row
    returned**. So we UNION one SELECT per rule, only materialising rows when
    the rule is violated.
    """
    trust = spec.trust
    table = _primary_source(spec)
    if trust is None or table is None:
        return (
            "-- No Trust rules to export for this metric, or no source table.\n"
            "select 1 where false\n"
        )

    # The dbt convention is ``{{ ref('model_name') }}`` — but we don't know the
    # user's model identifier, so we use ``{{ ref('<source>') }}`` by default
    # and flag it in the mapping doc for review.
    ref = "{{ ref('" + table + "') }}"
    header_lines = [
        "-- Generated by litmus from .metric — dbt singular test.",
        f"-- Source metric: {spec.name}",
        f"-- Primary source: {table}",
        "--",
        "-- Contract: every SELECT below returns rows ONLY when its rule is violated.",
        "-- dbt treats non-empty results as test failure, which is exactly what we want.",
        "",
    ]

    clauses: list[str] = []

    # ── freshness ──
    if trust.freshness:
        hours = trust.freshness.max_hours
        clauses.append(
            f"-- Freshness: updated_at must be within {hours:g}h\n"
            f"select 'freshness' as rule, "
            f"max(updated_at) as observed, "
            f"cast('{hours:g} hours' as varchar) as threshold\n"
            f"from {ref}\n"
            f"having extract(epoch from (current_timestamp - max(updated_at)))"
            f" / 3600.0 > {hours:g}"
        )
        mappings.append(RuleMapping(
            litmus_rule=f"Freshness < {hours:g} hours",
            dbt_target="singular_sql",
            note=(
                "Emitted as a HAVING clause. Consider `dbt_utils.recency` for a "
                "more idiomatic equivalent."
            ),
        ))

    # ── non-zero null-rate thresholds ──
    for null_rule in trust.null_rules:
        if null_rule.max_percentage == 0:
            continue  # covered by the model YAML's not_null
        col = null_rule.column
        thresh = null_rule.max_percentage
        clauses.append(
            f"-- Null rate on {col} must be < {thresh}%\n"
            f"select 'null_rate_{col}' as rule,\n"
            f"       cast(100.0 * count(case when {col} is null then 1 end)"
            f" / nullif(count(*), 0) as varchar) as observed,\n"
            f"       '< {thresh}%' as threshold\n"
            f"from {ref}\n"
            f"having 100.0 * count(case when {col} is null then 1 end)"
            f" / nullif(count(*), 0) > {thresh}"
        )

    # ── non-zero duplicate-rate thresholds ──
    for dup_rule in trust.duplicate_rules:
        if dup_rule.max_percentage == 0:
            continue
        col = dup_rule.column
        thresh = dup_rule.max_percentage
        clauses.append(
            f"-- Duplicate rate on {col} must be < {thresh}%\n"
            f"select 'duplicate_rate_{col}' as rule,\n"
            f"       cast(100.0 * (count(*) - count(distinct {col}))"
            f" / nullif(count(*), 0) as varchar) as observed,\n"
            f"       '< {thresh}%' as threshold\n"
            f"from {ref}\n"
            f"having 100.0 * (count(*) - count(distinct {col}))"
            f" / nullif(count(*), 0) > {thresh}"
        )

    # ── row-count volume (stateless lower bound, not day-over-day) ──
    for vol_rule in trust.volume_rules:
        clauses.append(
            f"-- Volume drop: {vol_rule.max_drop_percentage}% {vol_rule.period}"
            f" over {vol_rule.period}\n"
            "-- TODO: this rule compares today's count to yesterday's and cannot be\n"
            "-- expressed as a pure singular test. Run `litmus check` on a schedule\n"
            "-- to enforce this rule, or replace with a snapshot-based diff test.\n"
            "select 1 where false"
        )
        mappings.append(RuleMapping(
            litmus_rule=(
                f"Row count drop <{vol_rule.max_drop_percentage}%"
                f" {vol_rule.period}-over-{vol_rule.period}"
            ),
            dbt_target="todo",
            note=(
                "dbt has no built-in day-over-day count comparator. Keep enforcing "
                "this via `litmus check` in CI."
            ),
        ))

    # ── stateful rules: change / distribution_shift / schema_drift ──
    for change_rule in trust.change_rules:
        clauses.append(
            f"-- Value change: {change_rule.max_change_percentage}%"
            f" {change_rule.period} over {change_rule.period}\n"
            "-- TODO: requires the Litmus history store. Enforce via `litmus check`\n"
            "-- in CI (the stable singular-test form would need a dbt snapshot).\n"
            "select 1 where false"
        )
        mappings.append(RuleMapping(
            litmus_rule=(
                f"Value change <{change_rule.max_change_percentage}%"
                f" {change_rule.period}-over-{change_rule.period}"
            ),
            dbt_target="todo",
            note="Stateful — depends on Litmus history store. Run `litmus check` in CI.",
        ))

    for dist_rule in trust.distribution_shift_rules:
        clauses.append(
            f"-- Distribution shift: mean({dist_rule.column}) hasn't shifted > "
            f"{dist_rule.max_change_percentage}%\n"
            "-- TODO: requires the Litmus history store. Enforce via `litmus check`.\n"
            "select 1 where false"
        )
        mappings.append(RuleMapping(
            litmus_rule=(
                f"Distribution shift on {dist_rule.column}"
                f" <{dist_rule.max_change_percentage}%"
                f" {dist_rule.period}-over-{dist_rule.period}"
            ),
            dbt_target="todo",
            note="Stateful — depends on Litmus history store.",
        ))

    if trust.schema_drift is not None:
        clauses.append(
            "-- Schema drift: column list mustn't change run over run.\n"
            "-- TODO: dbt's `dbt_utils.equal_column_names` can get close, but the\n"
            "-- canonical enforcement lives in `litmus check` against the history store.\n"
            "select 1 where false"
        )
        mappings.append(RuleMapping(
            litmus_rule="Schema must not drift",
            dbt_target="todo",
            note=(
                "No pure-SQL equivalent; `dbt_utils.equal_column_names` is the "
                "closest third-party approximation."
            ),
        ))

    if not clauses:
        clauses.append("-- (No rules required a singular test.)\nselect 1 where false")

    body = "\nunion all\n".join(clauses)
    return "\n".join(header_lines) + body + "\n"


# ─────────────────── mapping-doc builder ────────────────────


def _build_mapping_markdown(spec: MetricSpec, mappings: list[RuleMapping]) -> str:
    lines: list[str] = []
    lines.append(f"# Litmus → dbt mapping: {spec.name}")
    lines.append("")
    lines.append(f"Source metric file: `{_slug(spec.name)}.metric`")
    lines.append("")
    lines.append("| Litmus rule | Mapped to | Notes |")
    lines.append("|---|---|---|")
    target_label = {
        "model_yaml": "`models/litmus/*.yml` column test",
        "singular_sql": "`tests/singular/*.sql` clause",
        "todo": "**TODO** (not expressible in pure dbt)",
    }
    for m in mappings:
        note = m.note.replace("|", "\\|").replace("\n", " ")
        lines.append(f"| {m.litmus_rule} | {target_label[m.dbt_target]} | {note} |")
    lines.append("")
    todos = [m for m in mappings if m.dbt_target == "todo"]
    if todos:
        lines.append("## Rules that still need `litmus check`")
        lines.append("")
        lines.append(
            "These rules depend on state that dbt doesn't track (history of prior "
            "runs, schema snapshots). Keep them enforced by running `litmus check` "
            "in CI alongside `dbt test`."
        )
        lines.append("")
        for t in todos:
            lines.append(f"- **{t.litmus_rule}** — {t.note}")
        lines.append("")
    return "\n".join(lines)


# ─────────────────── public API ─────────────────────────────


def export_to_dbt(spec: MetricSpec) -> DbtExportBundle:
    """Build the dbt artefacts for a single ``MetricSpec``."""
    mappings: list[RuleMapping] = []
    model_yaml = _build_model_yaml(spec, mappings)
    singular_sql = _build_singular_sql(spec, mappings)
    mapping_md = _build_mapping_markdown(spec, mappings)
    return DbtExportBundle(
        metric_slug=_slug(spec.name),
        model_yaml=model_yaml,
        singular_test_sql=singular_sql,
        mapping_markdown=mapping_md,
        mappings=mappings,
    )
