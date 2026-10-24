{{
  config(
    materialized='incremental',
    unique_key=['observed_hour'],
    incremental_strategy='merge',
    on_schema_change='sync_all_columns',
    tags=['marts', 'aqi', 'incremental']
  )
}}

{#
  mart_lahore_aqi
  ---------------
  Layer: intermediate → marts

  City-level Lahore AQI by UTC hour. Methodology: docs/aqi.md (US EPA AQI).

  Method:
  1. Average valid concentrations across stations per pollutant × hour.
  2. Re-score that hourly mean against EPA breakpoints (seed = Python table).
  3. Overall AQI = max pollutant sub-index (EPA reporting rule).
     Hours with no in-range sub-index produce no row (insufficient input).
  4. Expose pm25_rolling_24h_avg for EPA-aligned 24h PM context.

  Breakpoints are never invented here — see seeds/aqi_breakpoints.csv.
#}

with hourly_pollutant as (

    select
        observed_hour,
        pollutant,
        avg(value) as value_avg,
        max(unit) as unit,
        count(distinct station_id) as station_count,
        count(*) as observation_count,
        max(aqi_subindex) as aqi_subindex_max_station,
        avg(aqi_subindex) as aqi_subindex_avg_station
    from {{ ref('int_air_quality_aqi_subindex') }}
    {% if is_incremental() %}
      where observed_hour >= (
          select coalesce(
              max(observed_hour) - interval '26 hours',
              timestamp '1970-01-01 00:00:00+00'
          )
          from {{ this }}
      )
    {% endif %}
    group by observed_hour, pollutant

),

rescored as (

    select
        h.*,
        {{ truncate_aqi_concentration('h.pollutant', 'h.value_avg') }} as concentration_truncated,
        b.breakpoint_low,
        b.breakpoint_high,
        b.aqi_low,
        b.aqi_high
    from hourly_pollutant h
    left join {{ ref('aqi_breakpoints') }} b
        on b.pollutant = h.pollutant
       and {{ truncate_aqi_concentration('h.pollutant', 'h.value_avg') }} >= b.breakpoint_low
       and {{ truncate_aqi_concentration('h.pollutant', 'h.value_avg') }} <= b.breakpoint_high
       and (
            (h.pollutant in ('pm25', 'pm10') and h.unit = 'µg/m³' and b.unit = 'µg/m³')
            or (h.pollutant in ('o3', 'co') and lower(h.unit) = 'ppm' and b.unit = 'ppm')
            or (h.pollutant in ('so2', 'no2') and lower(h.unit) = 'ppb' and b.unit = 'ppb')
       )

),

with_subindex as (

    select
        observed_hour,
        pollutant,
        value_avg,
        unit,
        station_count,
        observation_count,
        {{ aqi_equation(
            'concentration_truncated',
            'breakpoint_low',
            'breakpoint_high',
            'aqi_low',
            'aqi_high'
        ) }} as aqi_subindex
    from rescored

),

ranked as (

    select
        *,
        row_number() over (
            partition by observed_hour
            order by aqi_subindex desc nulls last, pollutant
        ) as _aqi_rank
    from with_subindex
    where aqi_subindex is not null

),

city_aqi as (

    select
        observed_hour,
        aqi_subindex as aqi,
        pollutant as dominant_pollutant,
        value_avg as dominant_pollutant_value,
        unit as dominant_pollutant_unit,
        station_count,
        observation_count
    from ranked
    where _aqi_rank = 1

),

pm25_24h as (

    select
        observed_hour,
        avg(value_avg) over (
            order by observed_hour
            range between interval '23 hours' preceding and current row
        ) as pm25_rolling_24h_avg
    from with_subindex
    where pollutant = 'pm25'

)

select
    c.observed_hour,
    c.aqi,
    {{ aqi_category('c.aqi') }} as aqi_category,
    c.dominant_pollutant,
    c.dominant_pollutant_value,
    c.dominant_pollutant_unit,
    c.station_count,
    c.observation_count,
    p.pm25_rolling_24h_avg
from city_aqi c
left join pm25_24h p
    on p.observed_hour = c.observed_hour
{% if is_incremental() %}
where c.observed_hour >= (
    select coalesce(
        max(observed_hour) - interval '2 hours',
        timestamp '1970-01-01 00:00:00+00'
    )
    from {{ this }}
)
{% endif %}
