{{
  config(
    materialized='incremental',
    unique_key=['latitude', 'longitude', 'observed_hour', 'source_name'],
    incremental_strategy='merge',
    on_schema_change='sync_all_columns',
    tags=['marts', 'weather', 'incremental']
  )
}}

{#
  mart_weather_hourly
  -------------------
  Layer: intermediate → marts

  Hourly weather aggregates at rounded coordinates.
  Grain: (latitude, longitude, observed_hour, source_name).
#}

with base as (

    select *
    from {{ ref('int_weather_metrics_normalized') }}
    where has_any_metric
    {% if is_incremental() %}
      and observed_hour >= (
          select coalesce(
              max(observed_hour) - interval '2 hours',
              timestamp '1970-01-01 00:00:00+00'
          )
          from {{ this }}
      )
    {% endif %}

)

select
    latitude,
    longitude,
    observed_hour,
    source_name,
    avg(temperature_c) as temperature_c_avg,
    avg(relative_humidity_pct) as relative_humidity_pct_avg,
    sum(precipitation_mm) as precipitation_mm_sum,
    avg(wind_speed_ms) as wind_speed_ms_avg,
    avg(wind_direction_deg) as wind_direction_deg_avg,
    avg(pressure_hpa) as pressure_hpa_avg,
    count(*) as observation_count,
    max(ingested_at_utc) as last_ingested_at_utc
from base
group by
    latitude,
    longitude,
    observed_hour,
    source_name
