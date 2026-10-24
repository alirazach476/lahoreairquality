{#
  Map free-text / source pollutant labels to a canonical code.

  Business rules live here (and in seed pollutant_canonical_map), not inline in
  mart SQL. Unknown labels return null so upstream models can quarantine them.
#}
{% macro normalize_pollutant_code(pollutant_expr) -%}
  case
    when lower(trim({{ pollutant_expr }})) in ('pm25', 'pm2.5', 'pm_2_5', 'pm2_5', 'fine particulate matter')
      then 'pm25'
    when lower(trim({{ pollutant_expr }})) in ('pm10', 'pm10.0', 'pm_10', 'coarse particulate matter')
      then 'pm10'
    when lower(trim({{ pollutant_expr }})) in ('o3', 'ozone', 'o_3')
      then 'o3'
    when lower(trim({{ pollutant_expr }})) in ('no2', 'nitrogen dioxide', 'no_2')
      then 'no2'
    when lower(trim({{ pollutant_expr }})) in ('so2', 'sulfur dioxide', 'sulphur dioxide', 'so_2')
      then 'so2'
    when lower(trim({{ pollutant_expr }})) in ('co', 'carbon monoxide')
      then 'co'
    else null
  end
{%- endmacro %}
