{{
  config(
    materialized='view',
    tags=['intermediate', 'weather', 'metrics']
  )
}}

{#
  int_weather_metrics_normalized
  ------------------------------
  Layer: intermediate (weather normalization)

  Clamps / nulls physically impossible values and rounds coordinates for stable
  hourly aggregation keys. Does not invent missing measurements.
#}

select
    observation_sk,
    observed_at_utc,
    observed_hour,
    round(latitude::numeric, 4)::double precision as latitude,
    round(longitude::numeric, 4)::double precision as longitude,
    case
        when temperature_c between -90 and 60 then temperature_c
        else null
    end as temperature_c,
    case
        when relative_humidity_pct between 0 and 100 then relative_humidity_pct
        else null
    end as relative_humidity_pct,
    case
        when precipitation_mm >= 0 and precipitation_mm < 500 then precipitation_mm
        else null
    end as precipitation_mm,
    case
        when wind_speed_ms >= 0 and wind_speed_ms < 150 then wind_speed_ms
        else null
    end as wind_speed_ms,
    case
        when wind_direction_deg >= 0 and wind_direction_deg <= 360 then wind_direction_deg
        else null
    end as wind_direction_deg,
    case
        when pressure_hpa between 800 and 1100 then pressure_hpa
        else null
    end as pressure_hpa,
    source_name,
    ingested_at_utc,
    raw_record_id,
    (
        temperature_c is not null
        or relative_humidity_pct is not null
        or precipitation_mm is not null
        or wind_speed_ms is not null
        or wind_direction_deg is not null
        or pressure_hpa is not null
    ) as has_any_metric
from {{ ref('int_weather_timestamps_normalized') }}
