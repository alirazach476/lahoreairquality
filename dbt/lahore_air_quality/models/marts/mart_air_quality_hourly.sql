{{
  config(
    materialized='incremental',
    unique_key=['station_id', 'pollutant', 'observed_hour', 'source_name'],
    incremental_strategy='merge',
    on_schema_change='sync_all_columns',
    tags=['marts', 'air_quality', 'incremental']
  )
}}

{#
  mart_air_quality_hourly
  -----------------------
  Layer: intermediate → marts

  Hourly aggregates per station / pollutant for analytics dashboards.
  Grain: (station_id, pollutant, observed_hour, source_name).
#}

with base as (

    select *
    from {{ ref('int_air_quality_weather_joined') }}
    {% if is_incremental() %}
      where observed_hour >= (
          select coalesce(
              max(observed_hour) - interval '2 hours',
              timestamp '1970-01-01 00:00:00+00'
          )
          from {{ this }}
      )
    {% endif %}

),

aggregated as (

    select
        station_id,
        max(location_name) as location_name,
        avg(latitude) as latitude,
        avg(longitude) as longitude,
        pollutant,
        source_name,
        observed_hour,
        avg(value) as value_avg,
        min(value) as value_min,
        max(value) as value_max,
        count(*) as observation_count,
        avg(aqi_subindex) as aqi_subindex_avg,
        max(aqi_subindex) as aqi_subindex_max,
        max(unit) as unit,
        max(ingested_at_utc) as last_ingested_at_utc
    from base
    group by
        station_id,
        pollutant,
        source_name,
        observed_hour

)

select
    *,
    {{ aqi_category('aqi_subindex_max') }} as aqi_category
from aggregated
