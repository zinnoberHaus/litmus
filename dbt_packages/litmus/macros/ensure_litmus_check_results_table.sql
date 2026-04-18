{# ---------------------------------------------------------------------- #}
{# Idempotent CREATE TABLE IF NOT EXISTS for `litmus_check_results`.       #}
{# One row per rule per run. Joins to litmus_runs on `run_id`.             #}
{# ---------------------------------------------------------------------- #}

{% macro ensure_litmus_check_results_table() %}
    {% set tbl = litmus._litmus_table('litmus_check_results') %}
    {% set sql %}
        CREATE TABLE IF NOT EXISTS {{ tbl }} (
            id                  {{ litmus._varchar(36) }} NOT NULL,
            run_id              {{ litmus._varchar(36) }} NOT NULL,
            rule_type           {{ litmus._varchar(32) }} NOT NULL,
            rule_json           {{ litmus._varchar(4000) }} NOT NULL,
            status              {{ litmus._varchar(16) }} NOT NULL,
            message             {{ litmus._varchar(2000) }},
            actual_value        {{ litmus._decimal(38, 6) }},
            threshold_value     {{ litmus._decimal(38, 6) }},
            duration_ms         {{ litmus._integer() }}
        )
    {% endset %}
    {% do run_query(sql) %}
{% endmacro %}
