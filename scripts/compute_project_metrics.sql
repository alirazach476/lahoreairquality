-- Portfolio metrics — measured from warehouse only. No fabricated values.

\echo '=== AIR QUALITY RAW ==='
SELECT COUNT(*) AS total_aq_observations FROM raw.air_quality_observations;

SELECT
  COUNT(DISTINCT station_id) AS distinct_stations,
  COUNT(DISTINCT pollutant) AS distinct_pollutants,
  MIN(observed_at) AS min_observed_at,
  MAX(observed_at) AS max_observed_at,
  MIN(ingested_at) AS min_ingested_at,
  MAX(ingested_at) AS max_ingested_at
FROM raw.air_quality_observations;

SELECT pollutant, COUNT(*) AS n
FROM raw.air_quality_observations
GROUP BY pollutant
ORDER BY n DESC;

SELECT station_id, COALESCE(location_name, '') AS location_name, COUNT(*) AS n,
       MIN(observed_at) AS first_obs, MAX(observed_at) AS last_obs
FROM raw.air_quality_observations
GROUP BY station_id, location_name
ORDER BY n DESC;

\echo '=== AQ READINGS PER UTC DAY ==='
SELECT
  COUNT(*) AS days_with_data,
  ROUND(AVG(day_count)::numeric, 2) AS avg_readings_per_day,
  MIN(day_count) AS min_readings_per_day,
  MAX(day_count) AS max_readings_per_day,
  SUM(day_count) AS sum_check
FROM (
  SELECT date_trunc('day', observed_at AT TIME ZONE 'UTC') AS d, COUNT(*) AS day_count
  FROM raw.air_quality_observations
  GROUP BY 1
) s;

\echo '=== WEATHER RAW ==='
SELECT COUNT(*) AS total_weather_observations FROM raw.weather_observations;

SELECT
  MIN(observed_at) AS min_observed_at,
  MAX(observed_at) AS max_observed_at
FROM raw.weather_observations;

\echo '=== WEATHER READINGS PER UTC DAY ==='
SELECT
  COUNT(*) AS days_with_data,
  ROUND(AVG(day_count)::numeric, 2) AS avg_readings_per_day,
  MIN(day_count) AS min_readings_per_day,
  MAX(day_count) AS max_readings_per_day
FROM (
  SELECT date_trunc('day', observed_at AT TIME ZONE 'UTC') AS d, COUNT(*) AS day_count
  FROM raw.weather_observations
  GROUP BY 1
) s;

\echo '=== DUPLICATE RATE (AQ) ==='
-- Rows that share natural key would be blocked by UNIQUE; measure via raw_record_id collisions
-- and duplicate natural keys if any slipped in.
SELECT
  COUNT(*) AS total_rows,
  COUNT(DISTINCT (source, station_id, pollutant, observed_at)) AS distinct_natural_keys,
  COUNT(*) - COUNT(DISTINCT (source, station_id, pollutant, observed_at)) AS duplicate_natural_key_rows
FROM raw.air_quality_observations;

SELECT
  COUNT(*) AS total_rows,
  COUNT(DISTINCT raw_record_id) AS distinct_raw_record_ids,
  COUNT(*) - COUNT(DISTINCT raw_record_id) AS duplicate_raw_record_id_rows
FROM raw.air_quality_observations;

\echo '=== DUPLICATE RATE (WEATHER) ==='
SELECT
  COUNT(*) AS total_rows,
  COUNT(DISTINCT (source, latitude, longitude, observed_at)) AS distinct_natural_keys,
  COUNT(*) - COUNT(DISTINCT (source, latitude, longitude, observed_at)) AS duplicate_natural_key_rows
FROM raw.weather_observations;

\echo '=== SENSOR GAPS (hourly pm25 per station) ==='
-- For each station with pm25, count expected hourly slots vs present in [min,max]
WITH bounds AS (
  SELECT station_id,
         date_trunc('hour', MIN(observed_at)) AS t0,
         date_trunc('hour', MAX(observed_at)) AS t1,
         COUNT(*) AS n_pm25
  FROM raw.air_quality_observations
  WHERE pollutant IN ('pm25', 'pm2.5')
  GROUP BY station_id
),
hours AS (
  SELECT b.station_id, b.t0, b.t1, b.n_pm25,
         EXTRACT(EPOCH FROM (b.t1 - b.t0))/3600.0 + 1 AS expected_hours
  FROM bounds b
),
present AS (
  SELECT station_id,
         COUNT(DISTINCT date_trunc('hour', observed_at)) AS present_hours
  FROM raw.air_quality_observations
  WHERE pollutant IN ('pm25', 'pm2.5')
  GROUP BY station_id
)
SELECT h.station_id,
       h.n_pm25,
       ROUND(h.expected_hours::numeric, 0) AS expected_hours_span,
       p.present_hours,
       ROUND((p.present_hours / NULLIF(h.expected_hours, 0) * 100)::numeric, 2) AS pct_hours_present_in_span,
       ROUND((h.expected_hours - p.present_hours)::numeric, 0) AS missing_hour_slots_in_span
FROM hours h
JOIN present p USING (station_id)
ORDER BY h.n_pm25 DESC;

\echo '=== CITYWIDE AQ COMPLETENESS (distinct UTC hours with any AQ row) ==='
WITH span AS (
  SELECT date_trunc('hour', MIN(observed_at)) AS t0,
         date_trunc('hour', MAX(observed_at)) AS t1
  FROM raw.air_quality_observations
),
expected AS (
  SELECT EXTRACT(EPOCH FROM (t1 - t0))/3600.0 + 1 AS expected_hours FROM span
),
present AS (
  SELECT COUNT(DISTINCT date_trunc('hour', observed_at)) AS present_hours
  FROM raw.air_quality_observations
)
SELECT p.present_hours,
       ROUND(e.expected_hours::numeric, 0) AS expected_hours_span,
       ROUND((p.present_hours / NULLIF(e.expected_hours, 0) * 100)::numeric, 2) AS pct_hours_with_any_aq
FROM present p, expected e;

\echo '=== QUALITY MART IF PRESENT ==='
SELECT table_schema, table_name
FROM information_schema.tables
WHERE table_schema = 'quality' OR table_name ILIKE '%quality%';

\echo '=== MART / FORECAST COUNTS ==='
SELECT 'mart_lahore_aqi' AS t, COUNT(*) FROM marts.mart_lahore_aqi
UNION ALL SELECT 'mart_air_quality_hourly', COUNT(*) FROM marts.mart_air_quality_hourly
UNION ALL SELECT 'mart_weather_hourly', COUNT(*) FROM marts.mart_weather_hourly
UNION ALL SELECT 'mart_air_quality_features', COUNT(*) FROM marts.mart_air_quality_features
UNION ALL SELECT 'ml.forecasts', COUNT(*) FROM ml.forecasts;

\echo '=== PAYLOAD ARCHIVE ==='
SELECT COUNT(*) AS ingestion_payloads FROM raw.ingestion_payloads;
