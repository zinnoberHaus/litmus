{# ---------------------------------------------------------------------- #}
{# Idempotent CREATE TABLE IF NOT EXISTS for `litmus_runs`.                #}
{#                                                                         #}
{# Column types are the common subset of DuckDB / Postgres / Snowflake /   #}
{# BigQuery (see blueprint §2.2). We VARCHAR large JSON blobs rather than  #}
{# using JSONB/VARIANT/STRING-typed JSON so the DDL ships without          #}
{# per-adapter branches. Readers parse the JSON at read time.              #}
{# ---------------------------------------------------------------------- #}

{% macro ensure_litmus_runs_table() %}
    {% set tbl = litmus._litmus_table('litmus_runs') %}
    {% set sql %}
        CREATE TABLE IF NOT EXISTS {{ tbl }} (
            id                  {{ litmus._varchar(36) }} NOT NULL,
            metric_slug         {{ litmus._varchar(200) }} NOT NULL,
            metric_name         {{ litmus._varchar(500) }} NOT NULL,
            status              {{ litmus._varchar(16) }} NOT NULL,
            trust_score         {{ litmus._decimal(5, 4) }},
            started_at          {{ litmus._timestamp() }} NOT NULL,
            finished_at         {{ litmus._timestamp() }},
            commit_sha          {{ litmus._varchar(64) }},
            ci_run_id           {{ litmus._varchar(64) }},
            triggered_by        {{ litmus._varchar(32) }} NOT NULL,
            value_sum           {{ litmus._decimal(38, 6) }},
            row_count           {{ litmus._bigint() }},
            schema_fingerprint  {{ litmus._varchar(128) }},
            column_means_json   {{ litmus._varchar(16000) }},
            spec_json           {{ litmus._varchar(16000) }}
        )
    {% endset %}
    {% do run_query(sql) %}
{% endmacro %}
