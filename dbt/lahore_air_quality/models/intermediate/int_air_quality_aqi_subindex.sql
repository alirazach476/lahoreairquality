{{
  config(
    materialized='view',
    tags=['intermediate', 'air_quality', 'aqi']
  )
}}

{#
  int_air_quality_aqi_subindex
  ----------------------------
  Layer: intermediate (AQI — mirrors Python `lahore_air_quality.aqi`)

  Methodology: US EPA AQI (40 CFR 58 Appendix G + 2024 PM2.5 update).
  Full documentation: docs/aqi.md

  - Breakpoints: seed `aqi_breakpoints` (must match Python table).
  - Wrong unit / out-of-range truncated concentration → aqi_subindex NULL
    (never invent AQI > 500 or convert units).
  - Official EPA PM AQI uses a 24-hour average; this model scores the
    observation concentration for warehouse lineage. See mart_lahore_aqi
    for hourly vs rolling-24h products.
#}

with valid as (

    select *
    from {{ ref('int_air_quality_pollutants_normalized') }}
    where is_valid_pollutant

),

truncated as (

    select
        v.*,
        {{ truncate_aqi_concentration('v.pollutant', 'v.value') }} as concentration_truncated
    from valid v

),

with_breakpoints as (

    select
        t.*,
        b.breakpoint_low,
        b.breakpoint_high,
        b.aqi_low,
        b.aqi_high,
        b.category as aqi_category_for_breakpoint,
        b.unit as breakpoint_unit
    from truncated t
    left join {{ ref('aqi_breakpoints') }} b
        on b.pollutant = t.pollutant
       and t.concentration_truncated >= b.breakpoint_low
       and t.concentration_truncated <= b.breakpoint_high
       and (
            (t.pollutant in ('pm25', 'pm10') and t.unit = 'µg/m³' and b.unit = 'µg/m³')
            or (t.pollutant in ('o3', 'co') and lower(t.unit) = 'ppm' and b.unit = 'ppm')
            or (t.pollutant in ('so2', 'no2') and lower(t.unit) = 'ppb' and b.unit = 'ppb')
       )

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
    observed_at_utc,
    observed_hour,
    ingested_at_utc,
    source_name,
    raw_record_id,
    case
        when breakpoint_low is null then null
        else {{ aqi_equation(
            'concentration_truncated',
            'breakpoint_low',
            'breakpoint_high',
            'aqi_low',
            'aqi_high'
        ) }}
    end as aqi_subindex,
    case
        when breakpoint_low is null then null
        else aqi_category_for_breakpoint
    end as aqi_category,
    case
        when breakpoint_low is not null then 'ok'
        when pollutant in ('pm25', 'pm10')
            and unit = 'µg/m³'
            and concentration_truncated < 0 then 'below_supported_range'
        when pollutant = 'pm25'
            and unit = 'µg/m³'
            and concentration_truncated > 325.4 then 'above_supported_range'
        when pollutant = 'pm10'
            and unit = 'µg/m³'
            and concentration_truncated > 604 then 'above_supported_range'
        when pollutant in ('o3', 'co') and lower(unit) <> 'ppm' then 'invalid_unit'
        when pollutant in ('so2', 'no2') and lower(unit) <> 'ppb' then 'invalid_unit'
        when pollutant in ('pm25', 'pm10') and unit <> 'µg/m³' then 'invalid_unit'
        else 'insufficient_input'
    end as aqi_status
from with_breakpoints
