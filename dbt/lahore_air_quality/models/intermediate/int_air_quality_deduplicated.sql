{{
  config(
    materialized='view',
    tags=['intermediate', 'air_quality', 'deduplication']
  )
}}

{#
  int_air_quality_deduplicated
  ----------------------------
  Layer: staging → intermediate (deduplication)

  Keeps the latest ingested row per natural observation key
  (source, station, pollutant_raw, observed_at). Raw already enforces uniqueness;
  this model is defensive for replays / backfills that may relax constraints.
#}

with ordered as (

    select
        *,
        row_number() over (
            partition by source_name, station_id, pollutant_raw, observed_at
            order by ingested_at desc, observation_sk desc
        ) as _dedupe_rank
    from {{ ref('staging_air_quality') }}

)

select
    observation_sk,
    source_observation_id,
    station_id,
    location_name,
    latitude,
    longitude,
    pollutant_raw,
    value_raw,
    unit_raw,
    observed_at,
    ingested_at,
    source_name,
    raw_record_id
from ordered
where _dedupe_rank = 1
