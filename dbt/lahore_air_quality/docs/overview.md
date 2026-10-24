{% docs __overview__ %}

# Lahore Air Quality — dbt lineage

```text
raw (PostgreSQL)
  air_quality_observations
  weather_observations
        │
        ▼
staging
  staging_air_quality
  staging_weather
        │
        ▼
intermediate
  deduplication → timestamps → pollutant/weather normalization
  → AQI sub-index → AQ×weather join
        │
        ▼
marts
  mart_air_quality_hourly
  mart_weather_hourly
  mart_lahore_aqi
  mart_air_quality_features
```

## Design rules

- **Staging** renames/casts only.
- **Intermediate** owns dedupe, time grains, pollutant/weather rules, AQI math, joins.
- **Marts** aggregate for analytics; incremental where the grain is hourly.
- Breakpoints and alias maps live in **seeds**; formulas in **macros** — not scattered in mart SQL.

{% enddocs %}
