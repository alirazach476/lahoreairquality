{{
  config(
    materialized='view',
    tags=['intermediate', 'join']
  )
}}

{#
  int_air_quality_weather_joined
  ------------------------------
  Layer: intermediate (domain join)

  Attaches the best matching weather snapshot to each valid AQ observation:
  same UTC hour, nearest lat/lon (ties broken by latest ingestion).

  Weather is optional — AQ rows are preserved when no weather match exists.
#}

with aq as (

    select *
    from {{ ref('int_air_quality_aqi_subindex') }}

),

weather as (

    select *
    from {{ ref('int_weather_metrics_normalized') }}
    where has_any_metric

),

matched as (

    select
        aq.*,
        w.observation_sk as weather_observation_sk,
        w.temperature_c,
        w.relative_humidity_pct,
        w.precipitation_mm,
        w.wind_speed_ms,
        w.wind_direction_deg,
        w.pressure_hpa,
        w.latitude as weather_latitude,
        w.longitude as weather_longitude,
        w.source_name as weather_source_name,
        case
            when aq.latitude is not null
                and aq.longitude is not null
                and w.latitude is not null
                and w.longitude is not null
            then sqrt(
                power(aq.latitude - w.latitude, 2)
                + power(aq.longitude - w.longitude, 2)
            )
            else null
        end as geo_distance_deg,
        row_number() over (
            partition by aq.observation_sk
            order by
                case
                    when aq.latitude is not null
                        and aq.longitude is not null
                        and w.latitude is not null
                        and w.longitude is not null
                    then sqrt(
                        power(aq.latitude - w.latitude, 2)
                        + power(aq.longitude - w.longitude, 2)
                    )
                    else 999999
                end asc,
                w.ingested_at_utc desc
        ) as _weather_rank
    from aq
    left join weather w
        on w.observed_hour = aq.observed_hour

)

select
    observation_sk,
    source_observation_id,
    station_id,
    location_name,
    latitude,
    longitude,
    pollutant,
    value,
    unit,
    concentration_truncated,
    aqi_subindex,
    aqi_category,
    observed_at_utc,
    observed_hour,
    ingested_at_utc,
    source_name,
    raw_record_id,
    weather_observation_sk,
    temperature_c,
    relative_humidity_pct,
    precipitation_mm,
    wind_speed_ms,
    wind_direction_deg,
    pressure_hpa,
    weather_latitude,
    weather_longitude,
    weather_source_name,
    geo_distance_deg
from matched
where _weather_rank = 1
