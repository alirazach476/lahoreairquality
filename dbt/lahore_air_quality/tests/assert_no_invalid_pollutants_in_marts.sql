-- Marts must never expose unrecognized / invalid pollutant codes.
-- Intermediate keeps invalids for audit; analytics layers filter them out.

select pollutant
from {{ ref('mart_air_quality_hourly') }}
where pollutant not in ('pm25', 'pm10', 'o3', 'no2', 'so2', 'co')
   or pollutant is null
