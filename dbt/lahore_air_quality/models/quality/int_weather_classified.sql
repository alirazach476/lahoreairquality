{{
  config(
    materialized='view',
    tags=['quality', 'weather']
  )
}}

{#
  int_weather_classified
  ----------------------
  Classifies weather staging rows. Invalid/suspect retained — never deleted.
  Rules: docs/data-quality.md (mirrors lahore_air_quality.quality).
#}

with base as (

    select *
    from {{ ref('staging_weather') }}

),

dupes as (

    select
        source_name,
        latitude,
        longitude,
        observed_at,
        count(*) as key_count
    from {{ ref('staging_weather') }}
    group by 1, 2, 3, 4
    having count(*) > 1

),

flagged as (

    select
        b.*,
        (d.key_count is not null) as is_duplicate,
        (b.observed_at is null) as flag_missing_timestamp,
        (
            b.observed_at is not null
            and b.observed_at > (now() at time zone 'utc') + interval '1 hour'
        ) as flag_future_invalid,
        (
            b.observed_at is not null
            and b.observed_at > (now() at time zone 'utc') + interval '5 minutes'
            and b.observed_at <= (now() at time zone 'utc') + interval '1 hour'
        ) as flag_future_suspect,
        (
            (b.temperature_c is not null and (b.temperature_c < -90 or b.temperature_c > 60))
            or (b.relative_humidity_pct is not null and (b.relative_humidity_pct < 0 or b.relative_humidity_pct > 100))
            or (b.precipitation_mm is not null and (b.precipitation_mm < 0 or b.precipitation_mm > 500))
            or (b.wind_speed_ms is not null and (b.wind_speed_ms < 0 or b.wind_speed_ms > 150))
            or (b.wind_direction_deg is not null and (b.wind_direction_deg < 0 or b.wind_direction_deg > 360))
            or (b.pressure_hpa is not null and (b.pressure_hpa < 800 or b.pressure_hpa > 1100))
        ) as flag_abnormal_invalid
    from base b
    left join dupes d
        on d.source_name = b.source_name
       and d.latitude = b.latitude
       and d.longitude = b.longitude
       and d.observed_at = b.observed_at

),

classified as (

    select
        *,
        (
            flag_missing_timestamp
            or flag_future_invalid
            or flag_abnormal_invalid
        ) as is_invalid,
        (
            is_duplicate
            or flag_future_suspect
        ) as is_suspect
    from flagged

)

select
    *,
    {{ quality_class_from_flags('is_invalid', 'is_suspect') }} as quality_class
from classified
