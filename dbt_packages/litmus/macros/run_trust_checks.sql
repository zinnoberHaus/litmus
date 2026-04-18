{# ---------------------------------------------------------------------- #}
{# litmus.run_trust_checks()                                               #}
{# ---------------------------------------------------------------------- #}
{# Called from `on-run-end` in dbt_project.yml. Responsibilities:          #}
{#                                                                         #}
{#   1. Idempotently create the Litmus history tables                     #}
{#      (`litmus_runs`, `litmus_check_results`, `litmus_history`) so       #}
{#      the Python CLI + server have somewhere to write.                   #}
{#   2. Record that dbt just ran — a "triggered by dbt" marker that the    #}
{#      catalog UI can correlate with warehouse freshness.                 #}
{#                                                                         #}
{# We deliberately DO NOT re-implement trust-rule logic here in SQL. The   #}
{# Python CLI (`litmus check --backend warehouse`) owns the check-running  #}
{# semantics so we have a single source of truth. dbt's job is to provide  #}
{# the table shapes and the trigger point; users run                       #}
{#                                                                         #}
{#   dbt run                                                               #}
{#   litmus check metrics/ --backend warehouse                             #}
{#                                                                         #}
{# in sequence (or batch both in their CI workflow). See README.md.        #}
{# ---------------------------------------------------------------------- #}

{% macro run_trust_checks() %}
    {# Skip in parse/compile phases — only execute during `dbt run`. #}
    {% if not execute %}
        {{ return('') }}
    {% endif %}

    {# Ensure the three catalog tables exist before anyone tries to write. #}
    {% do litmus.ensure_litmus_runs_table() %}
    {% do litmus.ensure_litmus_check_results_table() %}
    {% do litmus.ensure_litmus_history_table() %}

    {# Emit a single 'dbt' run-marker so downstream readers know this
       warehouse was touched. The Python CLI adds rows of its own; this
       marker is the "dbt ran" signal distinct from "litmus check ran". #}
    {% do litmus.record_dbt_marker() %}

    {{ log("[litmus] run_trust_checks complete — history tables ready", info=True) }}
{% endmacro %}
