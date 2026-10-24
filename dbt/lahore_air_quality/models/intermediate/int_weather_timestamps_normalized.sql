{{
  config(
    materialized='view',
    tags=['intermediate', 'weather', 'timestamps']
  )
}}

{#
  int_weather_timestamps_normalized
  ---------------------------------
  Layer: intermediate (timestamp normalization)

  UTC event time + hourly bucket for joins with air quality.
#}

select
    observation_sk,
    observed_at as observed_at_utc,
    date_trunc('hour', observed_at) as observed_hour,
    latitude,
    longitude,
    temperature_c,
    relative_humidity_pct,
    precipitation_mm,
    wind_speed_ms,
    wind_direction_deg,
    pressure_hpa,
    source_name,
    ingested_at as ingested_at_utc,
    raw_record_id
from {{ ref('int_weather_deduplicated') }}
