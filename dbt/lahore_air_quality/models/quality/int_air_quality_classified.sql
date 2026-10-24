{{
  config(
    materialized='view',
    tags=['quality', 'air_quality']
  )
}}

{#
  int_air_quality_classified
  --------------------------
  Classifies every staging AQ row as valid | suspect | invalid.
  Suspicious / invalid rows are RETAINED — never deleted.
  Rules: docs/data-quality.md (mirrors lahore_air_quality.quality).
#}

with base as (

    select
        s.*,
        {{ normalize_pollutant_code('s.pollutant_raw') }} as pollutant_canonical,
        date_trunc('hour', s.observed_at) as observed_hour
    from {{ ref('staging_air_quality') }} s

),

weather_hours as (

    select distinct date_trunc('hour', observed_at) as observed_hour
    from {{ ref('staging_weather') }}

),

dupes as (

    select
        source_name,
        station_id,
        pollutant_raw,
        observed_at,
        count(*) as key_count
    from {{ ref('staging_air_quality') }}
    group by 1, 2, 3, 4
    having count(*) > 1

),

flagged as (

    select
        b.*,
        (d.key_count is not null) as is_duplicate,
        (w.observed_hour is null) as missing_weather,
        (b.observed_at is null) as flag_missing_timestamp,
        (b.value_raw is null) as flag_missing_value,
        (b.pollutant_canonical is null) as flag_unexpected_pollutant,
        (
            b.pollutant_canonical is not null
            and b.unit_raw is not null
            and not (
                (
                    b.pollutant_canonical in ('pm25', 'pm10')
                    and lower(b.unit_raw) in ('µg/m³', 'ug/m3', 'ug/m³', 'µg/m3')
                )
                or (
                    b.pollutant_canonical in ('o3', 'co')
                    and lower(b.unit_raw) = 'ppm'
                )
                or (
                    b.pollutant_canonical in ('so2', 'no2')
                    and lower(b.unit_raw) = 'ppb'
                )
            )
        ) as flag_unexpected_unit,
        (b.value_raw is not null and b.value_raw < 0) as flag_negative_concentration,
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
            b.pollutant_canonical = 'pm25' and b.value_raw > 2000
            or b.pollutant_canonical = 'pm10' and b.value_raw > 3000
            or b.pollutant_canonical = 'o3' and lower(b.unit_raw) = 'ppm' and b.value_raw > 1
            or b.pollutant_canonical = 'co' and lower(b.unit_raw) = 'ppm' and b.value_raw > 100
            or b.pollutant_canonical in ('so2', 'no2') and lower(b.unit_raw) = 'ppb' and b.value_raw > 5000
        ) as flag_abnormal_invalid,
        (
            b.pollutant_canonical = 'pm25' and b.value_raw > 325.4 and b.value_raw <= 2000
            or b.pollutant_canonical = 'pm10' and b.value_raw > 604 and b.value_raw <= 3000
            or b.pollutant_canonical = 'o3' and lower(b.unit_raw) = 'ppm' and b.value_raw > 0.200 and b.value_raw <= 1
            or b.pollutant_canonical = 'co' and lower(b.unit_raw) = 'ppm' and b.value_raw > 50.4 and b.value_raw <= 100
            or b.pollutant_canonical = 'so2' and lower(b.unit_raw) = 'ppb' and b.value_raw > 1004 and b.value_raw <= 5000
            or b.pollutant_canonical = 'no2' and lower(b.unit_raw) = 'ppb' and b.value_raw > 2049 and b.value_raw <= 5000
        ) as flag_abnormal_suspect
    from base b
    left join dupes d
        on d.source_name = b.source_name
       and d.station_id = b.station_id
       and d.pollutant_raw = b.pollutant_raw
       and d.observed_at = b.observed_at
    left join weather_hours w
        on w.observed_hour = b.observed_hour

),

classified as (

    select
        observation_sk,
        station_id,
        pollutant_raw,
        pollutant_canonical,
        value_raw,
        unit_raw,
        observed_at,
        observed_hour,
        ingested_at,
        source_name,
        raw_record_id,
        is_duplicate,
        missing_weather,
        flag_missing_timestamp,
        flag_missing_value,
        flag_unexpected_pollutant,
        flag_unexpected_unit,
        flag_negative_concentration,
        flag_future_invalid,
        flag_future_suspect,
        flag_abnormal_invalid,
        flag_abnormal_suspect,
        (
            flag_missing_timestamp
            or flag_missing_value
            or flag_unexpected_pollutant
            or flag_unexpected_unit
            or flag_negative_concentration
            or flag_future_invalid
            or flag_abnormal_invalid
        ) as is_invalid,
        (
            is_duplicate
            or missing_weather
            or flag_future_suspect
            or flag_abnormal_suspect
        ) as is_suspect
    from flagged

)

select
    *,
    {{ quality_class_from_flags('is_invalid', 'is_suspect') }} as quality_class
from classified
