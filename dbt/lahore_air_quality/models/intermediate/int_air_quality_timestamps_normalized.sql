{{
  config(
    materialized='view',
    tags=['intermediate', 'air_quality', 'timestamps']
  )
}}

{#
  int_air_quality_timestamps_normalized
  -------------------------------------
  Layer: intermediate (timestamp normalization)

  Ingestion stores timestamptz in UTC. We expose explicit UTC columns and an
  hourly grain for marts. No pollutant / AQI logic here.
#}

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
    observed_at as observed_at_utc,
    date_trunc('hour', observed_at) as observed_hour,
    ingested_at as ingested_at_utc,
    source_name,
    raw_record_id
from {{ ref('int_air_quality_deduplicated') }}
