{{
  config(
    materialized='table',
    tags=['quality', 'observability']
  )
}}

{#
  mart_data_quality_report
  ------------------------
  One-row observability snapshot over classified staging data.
  Does not delete or rewrite source observations.
#}

with aq as (

    select * from {{ ref('int_air_quality_classified') }}

),

wx as (

    select * from {{ ref('int_weather_classified') }}

),

aq_counts as (

    select
        count(*)::bigint as record_count,
        count(*) filter (where quality_class = 'valid')::bigint as valid_count,
        count(*) filter (where quality_class = 'suspect')::bigint as suspect_count,
        count(*) filter (where quality_class = 'invalid')::bigint as invalid_count,
        count(*) filter (where is_duplicate)::bigint as duplicate_row_count,
        count(*) filter (where observed_at is null)::bigint as null_observed_at,
        count(*) filter (where value_raw is null)::bigint as null_value,
        count(*) filter (where pollutant_raw is null)::bigint as null_pollutant,
        count(*) filter (where unit_raw is null)::bigint as null_unit,
        count(*) filter (where station_id is null)::bigint as null_station_id,
        count(*) filter (where missing_weather)::bigint as missing_weather_count,
        count(*) filter (where flag_future_invalid or flag_future_suspect)::bigint as future_timestamp_count,
        count(*) filter (where flag_negative_concentration)::bigint as negative_concentration_count,
        count(*) filter (where flag_abnormal_invalid or flag_abnormal_suspect)::bigint as abnormal_value_count,
        count(*) filter (where flag_unexpected_pollutant)::bigint as unexpected_pollutant_count,
        count(*) filter (where flag_unexpected_unit)::bigint as unexpected_unit_count,
        min(observed_at) as min_observed_at,
        max(observed_at) as max_observed_at,
        min(value_raw) as min_value,
        max(value_raw) as max_value
    from aq

),

wx_counts as (

    select
        count(*)::bigint as weather_record_count,
        count(*) filter (where quality_class = 'invalid')::bigint as weather_invalid_count,
        count(*) filter (where is_duplicate)::bigint as weather_duplicate_row_count,
        max(observed_at) as weather_max_observed_at
    from wx

),

sensor_latest as (

    select
        station_id,
        max(observed_at) as latest_observed_at
    from aq
    where station_id is not null
      and observed_at is not null
    group by station_id

),

sensor_activity as (

    select
        count(*)::bigint as stations_seen,
        count(*) filter (
            where latest_observed_at < (now() at time zone 'utc') - interval '6 hours'
        )::bigint as inactive_station_count
    from sensor_latest

),

distinct_hours as (

    select distinct observed_hour
    from aq
    where observed_hour is not null

),

hour_gaps as (

    select
        observed_hour as gap_start,
        lead(observed_hour) over (order by observed_hour) as gap_end,
        extract(
            epoch from (
                lead(observed_hour) over (order by observed_hour) - observed_hour
            )
        ) / 3600.0 as gap_hours
    from distinct_hours

),

missing_intervals as (

    select
        count(*)::bigint as missing_interval_count,
        coalesce(max(gap_hours), 0)::double precision as max_gap_hours
    from hour_gaps
    where gap_end is not null
      and gap_hours > 3  -- GAP_FACTOR * EXPECTED_AQ_INTERVAL (1h)

),

pollutant_extremes as (

    select
        coalesce(
            jsonb_object_agg(
                pollutant_canonical,
                jsonb_build_object(
                    'min', min_v,
                    'max', max_v,
                    'n', n
                )
            ),
            '{}'::jsonb
        ) as value_extremes
    from (
        select
            pollutant_canonical,
            min(value_raw) as min_v,
            max(value_raw) as max_v,
            count(*)::bigint as n
        from aq
        where pollutant_canonical is not null
          and value_raw is not null
        group by pollutant_canonical
    ) e

)

select
    (now() at time zone 'utc') as generated_at,
    a.record_count,
    a.valid_count,
    a.suspect_count,
    a.invalid_count,
    a.duplicate_row_count,
    a.null_observed_at,
    a.null_value,
    a.null_pollutant,
    a.null_unit,
    a.null_station_id,
    a.missing_weather_count,
    a.future_timestamp_count,
    a.negative_concentration_count,
    a.abnormal_value_count,
    a.unexpected_pollutant_count,
    a.unexpected_unit_count,
    a.min_observed_at,
    a.max_observed_at,
    a.min_value,
    a.max_value,
    case
        when a.max_observed_at is null then true
        when a.max_observed_at < (now() at time zone 'utc') - interval '12 hours' then true
        else false
    end as is_stale,
    extract(
        epoch from ((now() at time zone 'utc') - a.max_observed_at)
    ) / 3600.0 as freshness_lag_hours,
    s.stations_seen,
    s.inactive_station_count,
    m.missing_interval_count,
    m.max_gap_hours,
    w.weather_record_count,
    w.weather_invalid_count,
    w.weather_duplicate_row_count,
    w.weather_max_observed_at,
    p.value_extremes,
    'Suspicious and invalid rows are classified only — never deleted.'::text as notes
from aq_counts a
cross join wx_counts w
cross join sensor_activity s
cross join missing_intervals m
cross join pollutant_extremes p
