-- Pivoted pollutant feature columns must be non-negative when present.

select station_id, observed_hour, pm25, pm10, o3, no2, so2, co
from {{ ref('mart_air_quality_features') }}
where (pm25 is not null and pm25 < 0)
   or (pm10 is not null and pm10 < 0)
   or (o3 is not null and o3 < 0)
   or (no2 is not null and no2 < 0)
   or (so2 is not null and so2 < 0)
   or (co is not null and co < 0)
