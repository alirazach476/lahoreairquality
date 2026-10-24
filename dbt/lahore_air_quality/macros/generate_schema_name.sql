{#
  Use the custom schema name as written (staging / intermediate / marts / seeds)
  instead of prefixing with the target schema (e.g. public_staging).
#}
{% macro generate_schema_name(custom_schema_name, node) -%}
  {%- if custom_schema_name is none -%}
    {{ target.schema }}
  {%- else -%}
    {{ custom_schema_name | trim }}
  {%- endif -%}
{%- endmacro %}
