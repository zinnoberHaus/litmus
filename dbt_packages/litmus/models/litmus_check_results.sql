{#
  Thin view wrapper over the per-rule check results table. Joins to
  `litmus_runs` on `run_id`. Downstream users typically query this for
  dashboards ("how many freshness violations last week?").
#}

{{ config(
    materialized='view',
    alias='litmus_check_results_view',
    pre_hook=[
        "{{ litmus.ensure_litmus_check_results_table() }}",
    ]
) }}

select
    id,
    run_id,
    rule_type,
    rule_json,
    status,
    message,
    actual_value,
    threshold_value,
    duration_ms
from {{ litmus._litmus_table('litmus_check_results') }}
