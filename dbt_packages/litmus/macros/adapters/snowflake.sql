{# Snowflake — VARCHAR(n) works; BIGINT aliases to NUMBER(38,0). Decimal
   precision caps at 38, so ensure p <= 38. #}

{% macro snowflake__litmus_varchar(n) %}VARCHAR({{ n }}){% endmacro %}
{% macro snowflake__litmus_decimal(p, s) %}DECIMAL({{ p }}, {{ s }}){% endmacro %}
{% macro snowflake__litmus_bigint() %}NUMBER(38, 0){% endmacro %}
{% macro snowflake__litmus_integer() %}INTEGER{% endmacro %}
{% macro snowflake__litmus_timestamp() %}TIMESTAMP_NTZ{% endmacro %}
{% macro snowflake__litmus_current_timestamp() %}CURRENT_TIMESTAMP::TIMESTAMP_NTZ{% endmacro %}
