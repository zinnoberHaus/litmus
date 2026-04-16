# `litmus/generators/` — Code & text generation from `MetricSpec`

Turn a parsed `MetricSpec` (or an external manifest) into something else: plain-English docs, SQL, or `.metric` stubs.

## Modules

| File | Direction | Purpose |
|------|-----------|---------|
| `plain_english.py` | `MetricSpec` → human text | Powers `litmus explain`. Business-friendly summary for analysts and execs. |
| `sql_generator.py` | `MetricSpec` → SQL string | Lowers a metric definition to a representative SQL query. **Not** used for execution — purely for explainability. |
| `dbt_importer.py` | `manifest.json` → `list[MetricSpec]` | Powers `litmus import-dbt`. Bootstraps `.metric` files from an existing dbt project. |

## `plain_english.py`

Owned by the **litmus-advocate** agent. Output is read by non-engineers — keep the tone conversational, second-person, jargon-free.

Critical: **must stay in sync with the DSL.** Whenever the **litmus-architect** adds a new rule type, `explain()` needs a matching phrasing, or the generated docs silently drop the rule.

## `sql_generator.py`

Used by the **litmus-connector** agent (with Architect input). The generated SQL is dialect-agnostic — no `IFNULL` vs `NULLIF` branching, no warehouse-specific functions. If it can't be expressed in ANSI SQL, leave it as a comment.

## `dbt_importer.py`

Strategy, in order:

1. Read `manifest["metrics"]` (dbt ≥ 1.6 semantic layer).
2. Fall back to `manifest["nodes"]` where `resource_type == "model"`.
3. For each, emit a `MetricSpec` with:
   - Name and description from dbt.
   - Source tables from model refs.
   - Default trust rules (freshness, null-rate, volume) from repo defaults.
   - **`TODO` markers** for anything we can't infer (business description, owner, ranges).

**Never invent descriptions.** A wrong auto-generated description is worse than a visible TODO that forces human review.

## Design rules

- Generators are **read-only** on their inputs — never mutate `MetricSpec`.
- Output is deterministic: same input → same output, so generated `.metric` files diff cleanly.
- `dbt_importer` writes files via `generate_metric_file(spec) -> str`; filename derivation (`spec.name.lower().replace(" ", "_")`) lives in the CLI, not the generator.
