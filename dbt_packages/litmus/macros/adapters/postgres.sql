{# Postgres — native types match ANSI; we pin DECIMAL rather than NUMERIC
   because the Postgres adapter treats them as aliases and DECIMAL is the
   form our other dialects share. #}

{% macro postgres__litmus_varchar(n) %}VARCHAR({{ n }}){% endmacro %}
{% macro postgres__litmus_decimal(p, s) %}DECIMAL({{ p }}, {{ s }}){% endmacro %}
{% macro postgres__litmus_bigint() %}BIGINT{% endmacro %}
{% macro postgres__litmus_integer() %}INTEGER{% endmacro %}
{% macro postgres__litmus_timestamp() %}TIMESTAMP{% endmacro %}
{% macro postgres__litmus_current_timestamp() %}CURRENT_TIMESTAMP{% endmacro %}
