{{
  config(
    materialized='view',
    tags=['staging', 'air_quality']
  )
}}

{#
  staging_air_quality
  --------------------
  Layer: raw → staging

  Responsibility: light typing / renaming only. No dedupe, no AQI, no joins.
  Downstream intermediate models own business transforms.
#}

with source as (

    select *
    from {{ source('raw', 'air_quality_observations') }}

),

renamed as (

    select
        id as observation_sk,
        observation_id as source_observation_id,
        station_id,
        location_name,
        latitude::double precision as latitude,
        longitude::double precision as longitude,
        lower(trim(pollutant)) as pollutant_raw,
        value::double precision as value_raw,
        trim(unit) as unit_raw,
        observed_at,
        ingested_at,
        lower(trim(source)) as source_name,
        raw_record_id
    from source

)

select * from renamed
