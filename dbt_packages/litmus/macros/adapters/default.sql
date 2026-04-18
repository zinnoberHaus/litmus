{# ---------------------------------------------------------------------- #}
{# Default type-name primitives. Overridden per adapter in sibling files. #}
{#                                                                         #}
{# Each macro returns the DDL type name for this adapter. A dispatcher    #}
{# at the top of the package (`_varchar`, `_decimal`, etc.) picks the     #}
{# right override by inspecting `target.type`.                             #}
{# ---------------------------------------------------------------------- #}

{% macro default__litmus_varchar(n) %}VARCHAR({{ n }}){% endmacro %}
{% macro default__litmus_decimal(p, s) %}DECIMAL({{ p }}, {{ s }}){% endmacro %}
{% macro default__litmus_bigint() %}BIGINT{% endmacro %}
{% macro default__litmus_integer() %}INTEGER{% endmacro %}
{% macro default__litmus_timestamp() %}TIMESTAMP{% endmacro %}
{% macro default__litmus_current_timestamp() %}CURRENT_TIMESTAMP{% endmacro %}
