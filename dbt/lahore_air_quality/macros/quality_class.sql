{# Roll up boolean flags into valid | suspect | invalid (never deletes rows). #}
{% macro quality_class_from_flags(is_invalid_expr, is_suspect_expr) -%}
  case
    when {{ is_invalid_expr }} then 'invalid'
    when {{ is_suspect_expr }} then 'suspect'
    else 'valid'
  end
{%- endmacro %}
