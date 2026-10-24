{{
  config(
    materialized='view',
    tags=['intermediate', 'air_quality', 'pollutants']
  )
}}

{#
  int_air_quality_pollutants_normalized
  -------------------------------------
  Layer: intermediate (pollutant normalization)

  Maps source labels → canonical codes via macro (+ optional seed map),
  normalizes units for PM to µg/m³ where possible, and flags invalid rows.
  Invalid pollutants are retained with is_valid_pollutant = false so tests can
  assert they never reach analytics marts.
#}

with mapped as (

    select
        t.*,
        coalesce(
            {{ normalize_pollutant_code('t.pollutant_raw') }},
            m.canonical_pollutant
        ) as pollutant,
        case
            when coalesce(
                {{ normalize_pollutant_code('t.pollutant_raw') }},
                m.canonical_pollutant
            ) is null then false
            else true
        end as is_recognized_pollutant
    from {{ ref('int_air_quality_timestamps_normalized') }} t
    left join {{ ref('pollutant_canonical_map') }} m
        on lower(trim(m.source_pollutant)) = t.pollutant_raw

),

unit_normalized as (

    select
        observation_sk,
        source_observation_id,
        station_id,
        location_name,
        latitude,
        longitude,
        pollutant_raw,
        pollutant,
        is_recognized_pollutant,
        value_raw,
        unit_raw,
        case
            when pollutant in ('pm25', 'pm10')
                and lower(unit_raw) in ('µg/m³', 'ug/m3', 'ug/m³', 'µg/m3')
                then value_raw
            when pollutant in ('pm25', 'pm10')
                and lower(unit_raw) in ('mg/m3', 'mg/m³')
                then value_raw * 1000.0
            else value_raw
        end as value,
        case
            when pollutant in ('pm25', 'pm10')
                and lower(unit_raw) in ('µg/m³', 'ug/m3', 'ug/m³', 'µg/m3', 'mg/m3', 'mg/m³')
                then 'µg/m³'
            else unit_raw
        end as unit,
        observed_at_utc,
        observed_hour,
        ingested_at_utc,
        source_name,
        raw_record_id
    from mapped

),

validated as (

    select
        *,
        case
            when not is_recognized_pollutant then false
            when value is null then false
            when value < 0 then false
            -- Defensive physical ceilings (not AQI breakpoints).
            when pollutant = 'pm25' and value > 2000 then false
            when pollutant = 'pm10' and value > 3000 then false
            when pollutant = 'o3' and unit = 'ppm' and value > 1 then false
            when pollutant = 'co' and unit = 'ppm' and value > 100 then false
            when pollutant in ('so2', 'no2') and unit = 'ppb' and value > 5000 then false
            else true
        end as is_valid_pollutant
    from unit_normalized

)

select * from validated
