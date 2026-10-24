-- City AQI must stay within the EPA reporting band used by this project.

select observed_hour, aqi
from {{ ref('mart_lahore_aqi') }}
where aqi < 0 or aqi > 500
