{# ---------------------------------------------------------------------- #}
{# record_dbt_marker — write a "dbt ran at T" row into litmus_runs.        #}
{#                                                                         #}
{# This is the minimum viable signal that dbt touched the warehouse. The  #}
{# Python CLI's trust checks write fuller rows (with `triggered_by='cli'`  #}
{# or `'scheduled'`); the dbt-side marker uses `triggered_by='dbt'` so     #}
{# downstream consumers can filter.                                        #}
{#                                                                         #}
{# Portable INSERT ... SELECT form works across DuckDB/Postgres/Snowflake/ #}
{# BigQuery without needing per-adapter dialect macros.                    #}
{# ---------------------------------------------------------------------- #}

{% macro record_dbt_marker() %}
    {% set runs = litmus._litmus_table('litmus_runs') %}
    {% set sql %}
        INSERT INTO {{ runs }} (
            id, metric_slug, metric_name, status, trust_score,
            started_at, finished_at,
            commit_sha, ci_run_id, triggered_by,
            value_sum, row_count,
            schema_fingerprint, column_means_json, spec_json
        )
        SELECT
            '{{ invocation_id }}',
            '__dbt_run__',
            'dbt run marker',
            'passed',
            NULL,
            {{ litmus._current_timestamp() }},
            {{ litmus._current_timestamp() }},
            NULL,
            '{{ invocation_id }}',
            'dbt',
            NULL, NULL, NULL, NULL, NULL
    {% endset %}
    {% do run_query(sql) %}
{% endmacro %}
