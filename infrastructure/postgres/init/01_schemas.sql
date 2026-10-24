-- Bootstrap logical schemas for the Lahore AQI warehouse.
-- Table DDL is owned by Alembic migrations (see alembic/versions/).

CREATE SCHEMA IF NOT EXISTS raw;
CREATE SCHEMA IF NOT EXISTS staging;
CREATE SCHEMA IF NOT EXISTS intermediate;
CREATE SCHEMA IF NOT EXISTS marts;
CREATE SCHEMA IF NOT EXISTS ml;

COMMENT ON SCHEMA raw IS 'Append-friendly landing zone: raw payloads + normalized observations';
COMMENT ON SCHEMA staging IS 'dbt staging models';
COMMENT ON SCHEMA intermediate IS 'dbt intermediate models (joins, AQI, gap flags)';
COMMENT ON SCHEMA marts IS 'Analytics and API-facing tables';
COMMENT ON SCHEMA ml IS 'Feature tables and model predictions';
