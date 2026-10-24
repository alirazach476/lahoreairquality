{{
  config(
    materialized='view',
    tags=['intermediate', 'weather', 'deduplication']
  )
}}

{#
  int_weather_deduplicated
  ------------------------
  Layer: staging → intermediate (deduplication)

  Latest ingested row per (source, latitude, longitude, observed_at).
#}

with ordered as (

    select
        *,
        row_number() over (
            partition by source_name, latitude, longitude, observed_at
            order by ingested_at desc, observation_sk desc
        ) as _dedupe_rank
    from {{ ref('staging_weather') }}

)

select
    observation_sk,
    observed_at,
    latitude,
    longitude,
    temperature_c,
    relative_humidity_pct,
    precipitation_mm,
    wind_speed_ms,
    wind_direction_deg,
    pressure_hpa,
    source_name,
    ingested_at,
    raw_record_id
from ordered
where _dedupe_rank = 1
