-- Extensions required by the Lahore AQI persistence layer.
-- Runs once on first Postgres container initialization (lexicographic order).

CREATE EXTENSION IF NOT EXISTS "pgcrypto";
