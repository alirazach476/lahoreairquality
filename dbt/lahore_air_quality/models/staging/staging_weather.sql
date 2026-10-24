{{
  config(
    materialized='view',
    tags=['staging', 'weather']
  )
}}

{#
  staging_weather
  ---------------
  Layer: raw → staging

  Responsibility: light typing / renaming only. Metric cleaning happens in
  intermediate weather normalization.
#}

with source as (

    select *
    from {{ source('raw', 'weather_observations') }}

),

renamed as (

    select
        id as observation_sk,
        observed_at,
        latitude::double precision as latitude,
        longitude::double precision as longitude,
        temperature_c::double precision as temperature_c,
        relative_humidity_pct::double precision as relative_humidity_pct,
        precipitation_mm::double precision as precipitation_mm,
        wind_speed_ms::double precision as wind_speed_ms,
        wind_direction_deg::double precision as wind_direction_deg,
        pressure_hpa::double precision as pressure_hpa,
        lower(trim(source)) as source_name,
        ingested_at,
        raw_record_id
    from source

)

select * from renamed
