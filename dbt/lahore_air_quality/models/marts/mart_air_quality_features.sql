{{
  config(
    materialized='incremental',
    unique_key=['station_id', 'observed_hour'],
    incremental_strategy='merge',
    on_schema_change='sync_all_columns',
    tags=['marts', 'features', 'incremental']
  )
}}

{#
  mart_air_quality_features
  -------------------------
  Layer: intermediate → marts

  Wide feature table for analytics / future ML (ML training is out of scope).
  Grain: (station_id, observed_hour).

  Includes pivoted pollutant concentrations, station AQI, same-hour weather,
  and city-level AQI for that hour.
#}

with aq as (

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

station_hours as (

    select
        station_id,
        observed_hour,
        max(location_name) as location_name,
        avg(latitude) as latitude,
        avg(longitude) as longitude,
        max(source_name) as source_name,
        avg(case when pollutant = 'pm25' then value end) as pm25,
        avg(case when pollutant = 'pm10' then value end) as pm10,
        avg(case when pollutant = 'o3' then value end) as o3,
        avg(case when pollutant = 'no2' then value end) as no2,
        avg(case when pollutant = 'so2' then value end) as so2,
        avg(case when pollutant = 'co' then value end) as co,
        max(aqi_subindex) as station_aqi,
        avg(temperature_c) as temperature_c,
        avg(relative_humidity_pct) as relative_humidity_pct,
        avg(precipitation_mm) as precipitation_mm,
        avg(wind_speed_ms) as wind_speed_ms,
        avg(wind_direction_deg) as wind_direction_deg,
        avg(pressure_hpa) as pressure_hpa,
        count(*) as observation_count,
        max(ingested_at_utc) as last_ingested_at_utc
    from aq
    group by station_id, observed_hour

),

dominant as (

    select
        station_id,
        observed_hour,
        pollutant as station_dominant_pollutant,
        row_number() over (
            partition by station_id, observed_hour
            order by aqi_subindex desc nulls last, pollutant
        ) as _rank
    from aq
    where aqi_subindex is not null

)

select
    s.station_id,
    s.observed_hour,
    s.location_name,
    s.latitude,
    s.longitude,
    s.source_name,
    s.pm25,
    s.pm10,
    s.o3,
    s.no2,
    s.so2,
    s.co,
    s.station_aqi,
    {{ aqi_category('s.station_aqi') }} as station_aqi_category,
    d.station_dominant_pollutant,
    s.temperature_c,
    s.relative_humidity_pct,
    s.precipitation_mm,
    s.wind_speed_ms,
    s.wind_direction_deg,
    s.pressure_hpa,
    c.aqi as city_aqi,
    c.aqi_category as city_aqi_category,
    c.dominant_pollutant as city_dominant_pollutant,
    c.pm25_rolling_24h_avg,
    s.observation_count,
    s.last_ingested_at_utc
from station_hours s
left join dominant d
    on d.station_id = s.station_id
   and d.observed_hour = s.observed_hour
   and d._rank = 1
left join {{ ref('mart_lahore_aqi') }} c
    on c.observed_hour = s.observed_hour
