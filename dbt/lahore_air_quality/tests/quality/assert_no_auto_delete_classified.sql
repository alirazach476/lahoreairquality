-- Guardrail: classified layer must keep every staging row (no deletes).
-- Fails if classified count != staging count.

select
    'air_quality row count mismatch' as failure_reason
from (
    select
        (select count(*) from {{ ref('staging_air_quality') }}) as staging_n,
        (select count(*) from {{ ref('int_air_quality_classified') }}) as classified_n
) c
where staging_n <> classified_n

union all

select
    'weather row count mismatch' as failure_reason
from (
    select
        (select count(*) from {{ ref('staging_weather') }}) as staging_n,
        (select count(*) from {{ ref('int_weather_classified') }}) as classified_n
) c
where staging_n <> classified_n
