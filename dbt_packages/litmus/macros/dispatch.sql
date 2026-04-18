{# ---------------------------------------------------------------------- #}
{# Per-adapter type dispatch. Each helper uses dbt's built-in              #}
{# `adapter.dispatch` so that DuckDB, Postgres, Snowflake, and BigQuery    #}
{# targets pick up their own override from macros/adapters/*.sql.          #}
{#                                                                         #}
{# These are private (underscore-prefixed) — users shouldn't call them.    #}
{# ---------------------------------------------------------------------- #}

{% macro _varchar(n) %}
    {{ return(adapter.dispatch('litmus_varchar', 'litmus')(n)) }}
{% endmacro %}

{% macro _decimal(p, s) %}
    {{ return(adapter.dispatch('litmus_decimal', 'litmus')(p, s)) }}
{% endmacro %}

{% macro _bigint() %}
    {{ return(adapter.dispatch('litmus_bigint', 'litmus')()) }}
{% endmacro %}

{% macro _integer() %}
    {{ return(adapter.dispatch('litmus_integer', 'litmus')()) }}
{% endmacro %}

{% macro _timestamp() %}
    {{ return(adapter.dispatch('litmus_timestamp', 'litmus')()) }}
{% endmacro %}

{% macro _current_timestamp() %}
    {{ return(adapter.dispatch('litmus_current_timestamp', 'litmus')()) }}
{% endmacro %}

{# Fully-qualified table name honouring the user's schema override. We
   respect dbt's default model schema resolution — `{{ target.schema }}` is
   the right source of truth. If users set `+schema: litmus` in their
   dbt_project.yml under models.litmus, the tables land in
   `{target.schema}_litmus` (Elementary-style). #}
{% macro _litmus_table(name) %}
    {% set schema = generate_schema_name(none, none) %}
    {% if schema %}
        {{ return(adapter.quote(schema) ~ '.' ~ adapter.quote(name)) }}
    {% else %}
        {{ return(adapter.quote(name)) }}
    {% endif %}
{% endmacro %}
