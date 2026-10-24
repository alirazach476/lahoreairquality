{#
  Map a numeric AQI to the EPA category label (US AQI).
#}
{% macro aqi_category(aqi_expr) -%}
  case
    when {{ aqi_expr }} is null then null
    when {{ aqi_expr }} <= 50 then 'Good'
    when {{ aqi_expr }} <= 100 then 'Moderate'
    when {{ aqi_expr }} <= 150 then 'Unhealthy for Sensitive Groups'
    when {{ aqi_expr }} <= 200 then 'Unhealthy'
    when {{ aqi_expr }} <= 300 then 'Very Unhealthy'
    else 'Hazardous'
  end
{%- endmacro %}
