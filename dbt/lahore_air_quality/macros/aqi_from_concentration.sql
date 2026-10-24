{#
  Truncate a concentration for EPA AQI lookup (TAD truncation rules).

  Source of truth for breakpoints + behaviour: docs/aqi.md and
  Python package `lahore_air_quality.aqi` (unit-tested).
  Prefer joining `aqi_breakpoints` — see `int_air_quality_aqi_subindex`.
#}
{% macro truncate_aqi_concentration(pollutant_expr, concentration_expr) -%}
  case {{ pollutant_expr }}
    when 'pm25' then trunc({{ concentration_expr }}::numeric, 1)
    when 'pm10' then trunc({{ concentration_expr }}::numeric, 0)
    when 'o3' then trunc({{ concentration_expr }}::numeric, 3)
    when 'co' then trunc({{ concentration_expr }}::numeric, 1)
    when 'so2' then trunc({{ concentration_expr }}::numeric, 0)
    when 'no2' then trunc({{ concentration_expr }}::numeric, 0)
    else {{ concentration_expr }}::numeric
  end
{%- endmacro %}


{% macro aqi_equation(cp_expr, bp_lo, bp_hi, i_lo, i_hi) -%}
  case
    when {{ bp_hi }} = {{ bp_lo }} then {{ i_lo }}
    else round(
      (
        ({{ i_hi }} - {{ i_lo }})::numeric
        / nullif(({{ bp_hi }} - {{ bp_lo }})::numeric, 0)
      ) * ({{ cp_expr }} - {{ bp_lo }})
      + {{ i_lo }}
    )::integer
  end
{%- endmacro %}
