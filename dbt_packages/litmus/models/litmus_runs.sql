{#
  Placeholder model — deliberately empty.

  The `litmus_runs` warehouse table is created by the `on-run-end` hook
  (`litmus.run_trust_checks` → `litmus.ensure_litmus_runs_table`). We keep
  this file so dbt users can still `{{ ref('litmus_runs') }}` in a custom
  model, but we materialise it as a view that simply selects from the
  macro-managed base table to avoid a name collision.

  Users who want a dbt-materialised copy can override this model in their
  own project with `config(materialized='table')`. For v0.3 we ship the
  thin view path.
#}

{{ config(
    materialized='view',
    alias='litmus_runs_view',
    pre_hook=[
        "{{ litmus.ensure_litmus_runs_table() }}",
    ]
) }}

select
    id,
    metric_slug,
    metric_name,
    status,
    trust_score,
    started_at,
    finished_at,
    commit_sha,
    ci_run_id,
    triggered_by,
    value_sum,
    row_count,
    schema_fingerprint,
    column_means_json,
    spec_json
from {{ litmus._litmus_table('litmus_runs') }}
