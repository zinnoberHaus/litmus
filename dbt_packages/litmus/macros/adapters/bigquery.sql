{# BigQuery — STRING replaces VARCHAR(N); INT64/FLOAT64/NUMERIC replace
   BIGINT/DECIMAL. BigQuery's NUMERIC is fixed at (38, 9) precision and
   doesn't accept user (p, s) — we ignore those arguments and use NUMERIC. #}

{% macro bigquery__litmus_varchar(n) %}STRING{% endmacro %}
{% macro bigquery__litmus_decimal(p, s) %}NUMERIC{% endmacro %}
{% macro bigquery__litmus_bigint() %}INT64{% endmacro %}
{% macro bigquery__litmus_integer() %}INT64{% endmacro %}
{% macro bigquery__litmus_timestamp() %}TIMESTAMP{% endmacro %}
{% macro bigquery__litmus_current_timestamp() %}CURRENT_TIMESTAMP(){% endmacro %}
