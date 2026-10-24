# Data sources

## Air quality — OpenAQ API v3

Documentation: [docs.openaq.org](https://docs.openaq.org/)

| Item | Value |
|------|--------|
| Base URL | `OPENAQ_BASE_URL` (default `https://api.openaq.org`) |
| Auth | Header `X-API-Key: $OPENAQ_API_KEY` |
| Version | **v3** (v1/v2 deprecated) |
| Free rate limits | 60/min, 2,000/hour (see OpenAQ rate-limit docs) |

### Endpoints used by this project

| Purpose | Method / path |
|---------|----------------|
| Discover monitors near Lahore | `GET /v3/locations?coordinates=…&radius=…&iso=PK` |
| Recent values at a location | `GET /v3/locations/{locations_id}/latest` |
| Historical values for a sensor | `GET /v3/sensors/{sensors_id}/measurements` |

Lahore coverage is **discovered at runtime** from coordinates around the
configurable `LAHORE_LATITUDE` / `LAHORE_LONGITUDE` (25 km radius, Pakistan ISO).
Sensor/location IDs are never hard-coded.

Obtain a key at [explore.openaq.org/register](https://explore.openaq.org/register)
and set `OPENAQ_API_KEY` in `.env`.

Client code: `ingestion/poller/src/lahore_aqi_poller/clients/openaq/`.

## Weather — Open-Meteo

Documentation:

- Forecast / current: [open-meteo.com/en/docs](https://open-meteo.com/en/docs)
- Historical archive: [open-meteo.com/en/docs/historical-weather-api](https://open-meteo.com/en/docs/historical-weather-api)

| Variable | Purpose |
|----------|---------|
| `OPENMETEO_BASE_URL` | Forecast API host (default `https://api.open-meteo.com`) |
| `OPENMETEO_ARCHIVE_BASE_URL` | Archive API host (default `https://archive-api.open-meteo.com`) |
| `LAHORE_LATITUDE` / `LAHORE_LONGITUDE` | Configurable WGS84 target (defaults to Lahore centre) |

No API key is required for the public Open-Meteo endpoints.

### Endpoints used

| Purpose | Method / path |
|---------|----------------|
| Current + forecast hourly | `GET /v1/forecast` |
| Historical hourly | `GET /v1/archive` |

### ML weather variables requested

`temperature_2m`, `relative_humidity_2m`, `precipitation`, `wind_speed_10m`
(with `wind_speed_unit=ms`), `wind_direction_10m`, `surface_pressure`.

Client code: `ingestion/poller/src/lahore_aqi_poller/clients/openmeteo/`.

## Credentials

Supply secrets via `.env.example` / `lahore_air_quality.config.Settings`.
Never commit real secrets. Never log API keys.
