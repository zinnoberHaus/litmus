"""Import metric definitions from a dbt manifest.json and generate .metric files."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from litmus.spec.metric_spec import (
    ChangeRule,
    FreshnessRule,
    MetricSpec,
    NullRule,
    TrustSpec,
    VolumeRule,
)

# ---------------------------------------------------------------------------
# Lineage extraction
# ---------------------------------------------------------------------------


@dataclass
class LineageNodeSpec:
    """One node in a metric's lineage graph, as extracted from dbt.

    ``id`` is the dbt unique_id when available (``model.project.orders``) or
    a synthetic ``metric:<name>`` / ``source:<table>`` string otherwise.
    ``kind`` matches the API contract: ``"source"`` | ``"model"`` | ``"metric"``.
    """

    id: str
    label: str
    kind: str


@dataclass
class LineageEdgeSpec:
    """Directed edge: ``from_id`` → ``to_id``. Both ids must appear in nodes."""

    from_id: str
    to_id: str


@dataclass
class Lineage:
    nodes: list[LineageNodeSpec] = field(default_factory=list)
    edges: list[LineageEdgeSpec] = field(default_factory=list)


_MAX_LINEAGE_HOPS = 3


def _dbt_unique_id_to_node(unique_id: str, manifest: dict[str, Any]) -> LineageNodeSpec:
    """Resolve a dbt ``unique_id`` (e.g. ``model.project.orders``) to a lineage node.

    The kind comes from the prefix — ``source.*`` becomes ``"source"``, anything
    else (models, seeds, snapshots) becomes ``"model"``. The label is the short
    name so the UI shows ``orders`` rather than ``model.project.orders``.
    """
    nodes = manifest.get("nodes", {})
    sources = manifest.get("sources", {})

    if unique_id.startswith("source."):
        data = sources.get(unique_id, {})
        label = data.get("name") or data.get("identifier") or unique_id.split(".")[-1]
        return LineageNodeSpec(id=unique_id, label=label, kind="source")

    data = nodes.get(unique_id, {})
    label = data.get("name") or unique_id.split(".")[-1]
    return LineageNodeSpec(id=unique_id, label=label, kind="model")


def build_lineage(manifest: dict[str, Any], metric_name: str) -> Lineage:
    """Walk the manifest's ``parent_map`` up to 3 hops and return the subgraph.

    ``metric_name`` is the short dbt metric name (``total_revenue``), not the
    Litmus display name. We accept either the dbt metrics-section name or a
    model name — fallback lookup walks both.

    The returned graph always includes a synthetic terminal node
    ``metric:<name>`` so the UI can render the metric as the "leaf" regardless
    of whether the underlying dbt object is a metric or a model.
    """
    parent_map: dict[str, list[str]] = manifest.get("parent_map", {}) or {}
    metrics_section: dict[str, Any] = manifest.get("metrics", {}) or {}
    nodes_section: dict[str, Any] = manifest.get("nodes", {}) or {}

    # Resolve the starting dbt unique_id for this metric. Try the metrics
    # section first (dbt ≥ 1.6), then fall back to a model named the same.
    start_unique_id: str | None = None
    start_display: str = metric_name
    for uid, data in metrics_section.items():
        if data.get("name") == metric_name or data.get("label") == metric_name:
            start_unique_id = uid
            start_display = data.get("label") or data.get("name") or metric_name
            break
    if start_unique_id is None:
        for uid, data in nodes_section.items():
            if (
                data.get("resource_type") == "model"
                and data.get("name") == metric_name
            ):
                start_unique_id = uid
                start_display = data.get("name") or metric_name
                break

    # Always create the metric terminal node. If we can't resolve the start in
    # the manifest, we still return a degenerate graph (just the metric node)
    # — empty is never the right answer for lineage.
    metric_node = LineageNodeSpec(
        id=f"metric:{metric_name}",
        label=start_display,
        kind="metric",
    )

    if start_unique_id is None:
        return Lineage(nodes=[metric_node], edges=[])

    # BFS up the parent_map for up to _MAX_LINEAGE_HOPS hops. We record edges
    # pointing *downstream* (parent → child) which is the natural reading
    # direction for lineage (source flows into metric).
    nodes_by_id: dict[str, LineageNodeSpec] = {}
    edges: list[LineageEdgeSpec] = []
    frontier: list[tuple[str, int]] = [(start_unique_id, 0)]
    seen: set[str] = {start_unique_id}

    # The start node itself (either the dbt metric or the dbt model) gets
    # resolved first so it has a real label.
    nodes_by_id[start_unique_id] = _dbt_unique_id_to_node(start_unique_id, manifest)

    while frontier:
        current_id, depth = frontier.pop(0)
        if depth >= _MAX_LINEAGE_HOPS:
            continue
        for parent_id in parent_map.get(current_id, []) or []:
            if parent_id not in nodes_by_id:
                nodes_by_id[parent_id] = _dbt_unique_id_to_node(parent_id, manifest)
            edges.append(LineageEdgeSpec(from_id=parent_id, to_id=current_id))
            if parent_id not in seen:
                seen.add(parent_id)
                frontier.append((parent_id, depth + 1))

    # Finally, connect the resolved start node to the synthetic metric node so
    # the UI always sees a "metric" leaf at the end.
    edges.append(LineageEdgeSpec(from_id=start_unique_id, to_id=metric_node.id))

    all_nodes = list(nodes_by_id.values()) + [metric_node]
    return Lineage(nodes=all_nodes, edges=edges)


def import_dbt_manifest(manifest_path: str | Path) -> list[MetricSpec]:
    """Read a dbt manifest.json and extract metric definitions.

    For each metric/model found, generate a MetricSpec with:
    - Name and description from dbt
    - Source tables from model refs
    - Conditions inferred from filters
    - Trust rules with sensible defaults
    """
    path = Path(manifest_path)
    with open(path) as f:
        manifest = json.load(f)

    specs: list[MetricSpec] = []

    # Try dbt metrics section first (dbt >= 1.6 semantic layer)
    metrics = manifest.get("metrics", {})
    for key, metric_data in metrics.items():
        spec = _parse_dbt_metric(metric_data)
        if spec:
            specs.append(spec)

    # If no metrics section, fall back to models
    if not specs:
        nodes = manifest.get("nodes", {})
        for key, node in nodes.items():
            if node.get("resource_type") == "model":
                spec = _parse_dbt_model(node)
                if spec:
                    specs.append(spec)

    return specs


def _parse_dbt_metric(data: dict) -> MetricSpec | None:
    """Parse a dbt metric definition into a MetricSpec."""
    name = data.get("name", data.get("label", ""))
    if not name:
        return None

    description = data.get("description", "")
    tags = data.get("tags", [])

    # Extract source tables from depends_on
    sources = []
    depends = data.get("depends_on", {})
    for ref in depends.get("nodes", []):
        # refs look like "model.project.model_name"
        parts = ref.split(".")
        if len(parts) >= 3:
            sources.append(parts[-1])

    # Extract filters as conditions
    conditions = []
    for filt in data.get("filters", []):
        field = filt.get("field", "")
        operator = filt.get("operator", "=")
        value = filt.get("value", "")
        conditions.append(f'{field} {operator} "{value}"')

    # Infer calculations from metric type
    calculations = []
    metric_type = data.get("type", data.get("calculation_method", ""))
    expression = data.get("expression", data.get("sql", ""))
    if metric_type and expression:
        calculations.append(f"{metric_type}({expression})")

    # Default trust rules
    trust = TrustSpec(
        freshness=FreshnessRule(max_hours=24),
        null_rules=[],
        volume_rules=[VolumeRule(table=None, max_drop_percentage=25, period="day")],
        range_rules=[],
        change_rules=[ChangeRule(max_change_percentage=50, period="month")],
    )

    return MetricSpec(
        name=name.replace("_", " ").title(),
        description=description or None,
        owner=data.get("meta", {}).get("owner"),
        tags=tags,
        sources=sources,
        conditions=conditions,
        calculations=calculations,
        result_name=name.replace("_", " ").title(),
        trust=trust,
    )


def _parse_dbt_model(node: dict) -> MetricSpec | None:
    """Parse a dbt model node into a MetricSpec (best-effort)."""
    name = node.get("name", "")
    if not name:
        return None

    description = node.get("description", "")
    tags = node.get("tags", [])

    # Use the model name as the source table
    sources = [name]

    # Extract column descriptions for conditions
    conditions = []
    columns = node.get("columns", {})
    for col_name, col_data in columns.items():
        if col_data.get("description"):
            conditions.append(f'{col_name}: {col_data["description"]}')

    # Default trust
    trust = TrustSpec(
        freshness=FreshnessRule(max_hours=24),
        null_rules=[],
        volume_rules=[VolumeRule(table=None, max_drop_percentage=25, period="day")],
        range_rules=[],
        change_rules=[],
    )

    # Add null rules for columns with not_null tests
    for col_name, col_data in columns.items():
        tests = col_data.get("tests", [])
        if "not_null" in tests or any(
            isinstance(t, dict) and "not_null" in t for t in tests
        ):
            trust.null_rules.append(NullRule(column=col_name, max_percentage=0))

    return MetricSpec(
        name=name.replace("_", " ").title(),
        description=description or None,
        owner=node.get("meta", {}).get("owner"),
        tags=tags,
        sources=sources,
        conditions=conditions,
        calculations=[],
        result_name=name.replace("_", " ").title(),
        trust=trust,
    )


def generate_metric_file(spec: MetricSpec) -> str:
    """Generate a .metric file string from a MetricSpec."""
    lines: list[str] = []

    lines.append(f"Metric: {spec.name}")
    if spec.description:
        lines.append(f"Description: {spec.description}")
    if spec.owner:
        lines.append(f"Owner: {spec.owner}")
    if spec.tags:
        lines.append(f"Tags: {', '.join(spec.tags)}")

    lines.append("")
    lines.append(f"Source: {', '.join(spec.sources)}")

    lines.append("")
    if spec.conditions:
        lines.append(f"Given {spec.conditions[0]}")
        for cond in spec.conditions[1:]:
            lines.append(f"  And {cond}")
    else:
        source = spec.sources[0] if spec.sources else 'source'
        lines.append(
            f"Given all records from {source} table"
        )

    lines.append("")
    lines.append("When we calculate")
    if spec.calculations:
        lines.append(f"  Then {spec.calculations[0]}")
        for calc in spec.calculations[1:]:
            lines.append(f"  And {calc}")
    else:
        lines.append("  Then compute the metric  # TODO: add calculation steps")

    lines.append("")
    lines.append(f'The result is "{spec.result_name or spec.name}"')

    if spec.trust:
        lines.append("")
        lines.append("Trust:")
        if spec.trust.freshness:
            lines.append(f"  Freshness must be less than {spec.trust.freshness.max_hours:g} hours")
        for null_rule in spec.trust.null_rules:
            if null_rule.max_percentage == 0:
                lines.append(f"  Null rate on {null_rule.column} must be 0%")
            else:
                lines.append(
                    f"  Null rate on {null_rule.column}"
                    f" must be less than {null_rule.max_percentage:g}%"
                )
        for volume_rule in spec.trust.volume_rules:
            table_part = f" of {volume_rule.table}" if volume_rule.table else ""
            lines.append(
                f"  Row count{table_part} must not drop more than "
                f"{volume_rule.max_drop_percentage:g}%"
                f" {volume_rule.period} over {volume_rule.period}"
            )
        for range_rule in spec.trust.range_rules:
            lines.append(
                f"  Value must be between {range_rule.min_value:g}"
                f" and {range_rule.max_value:g}"
            )
        for change_rule in spec.trust.change_rules:
            lines.append(
                f"  Value must not change more than {change_rule.max_change_percentage:g}% "
                f"{change_rule.period} over {change_rule.period}"
            )

    lines.append("")
    return "\n".join(lines)
