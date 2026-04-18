{# DuckDB — accepts the default types; kept for symmetry + future tweaks. #}

{% macro duckdb__litmus_varchar(n) %}VARCHAR{% endmacro %}
{% macro duckdb__litmus_decimal(p, s) %}DECIMAL({{ p }}, {{ s }}){% endmacro %}
{% macro duckdb__litmus_bigint() %}BIGINT{% endmacro %}
{% macro duckdb__litmus_integer() %}INTEGER{% endmacro %}
{% macro duckdb__litmus_timestamp() %}TIMESTAMP{% endmacro %}
{% macro duckdb__litmus_current_timestamp() %}CURRENT_TIMESTAMP{% endmacro %}
