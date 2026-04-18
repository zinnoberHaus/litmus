{# ---------------------------------------------------------------------- #}
{# Idempotent CREATE TABLE IF NOT EXISTS for `litmus_history`.             #}
{#                                                                         #}
{# This is the table the Python `WarehouseHistoryStore` reads and writes   #}
{# (change rules, schema drift, distribution shift). Schema mirrors the    #}
{# SQLite fallback in `litmus/checks/history.py`. Keep both in sync.       #}
{# ---------------------------------------------------------------------- #}

{% macro ensure_litmus_history_table() %}
    {% set tbl = litmus._litmus_table('litmus_history') %}
    {% set sql %}
        CREATE TABLE IF NOT EXISTS {{ tbl }} (
            metric_name         {{ litmus._varchar(500) }} NOT NULL,
            value_sum           {{ litmus._decimal(38, 6) }},
            row_count           {{ litmus._bigint() }},
            recorded_at         {{ litmus._varchar(64) }} NOT NULL,
            run_id              {{ litmus._varchar(128) }},
            commit_sha          {{ litmus._varchar(128) }},
            schema_fingerprint  {{ litmus._varchar(4000) }},
            column_means_json   {{ litmus._varchar(16000) }}
        )
    {% endset %}
    {% do run_query(sql) %}
{% endmacro %}
