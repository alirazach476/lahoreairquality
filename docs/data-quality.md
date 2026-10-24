# Data quality & observability

Suspicious and invalid observations are **classified and retained**. The platform
never automatically deletes source rows based on quality rules.

| Layer | Location |
|-------|----------|
| Python (source of truth, unit-tested) | `src/lahore_air_quality/quality/` |
| Production monitor (Postgres) | `quality/monitor.py` + `python -m lahore_air_quality.quality` |
| dbt classified views + report | `dbt/.../models/quality/` |
| Thresholds | `quality/thresholds.py` (mirrored in dbt SQL) |

### Production vs tests

| Context | Data source |
|---------|-------------|
| Production monitor | `raw.air_quality_observations` + `raw.weather_observations` only |
| Unit tests | In-memory / mocked records and pytest fixtures (never used by the monitor) |
| Empty database | Status `NO_DATA_AVAILABLE` — **no synthetic rows are generated** |

```bash
python -m lahore_air_quality.quality
python -m lahore_air_quality.quality --json
```

If tables are empty, bootstrap real history first: [`bootstrap-history.md`](bootstrap-history.md).

Disposition classes: **`valid`** | **`suspect`** | **`invalid`**.

Roll-up: any **invalid** finding → `invalid`; else any **suspect** finding →
`suspect`; else `valid`.

---

## Air-quality rules

| Rule id | Severity | Condition |
|---------|----------|-----------|
| `missing_timestamp` | invalid | `observed_at` is null |
| `missing_value` | invalid | concentration missing or non-numeric |
| `future_timestamp` | invalid | `observed_at` > now UTC + **1 hour** |
| `future_timestamp` | suspect | now + **5 min** < `observed_at` ≤ now + **1 hour** |
| `unexpected_pollutant` | invalid | missing or not in `{pm25, pm10, o3, no2, so2, co}` |
| `unexpected_unit` | invalid | unit not allowed for that pollutant (see below) |
| `negative_concentration` | invalid | value &lt; 0 |
| `abnormal_value` | invalid | value above physical ceiling |
| `abnormal_value` | suspect | value above EPA AQI≤500 high, at/below ceiling |
| `duplicate_observation` | suspect | natural key already present (row kept) |
| `delayed_ingest` | suspect | `ingested_at − observed_at` &gt; **6 h** (late/backfill; row kept) |
| `missing_weather` | suspect | no weather observation for the same UTC hour |

### Expected units

| Pollutant | Units |
|-----------|--------|
| pm25, pm10 | `µg/m³` (aliases: `ug/m3`, `ug/m³`, `µg/m3`) |
| o3, co | `ppm` |
| so2, no2 | `ppb` |

### Abnormal ceilings

| Pollutant | Suspect above (EPA AQI 500 high) | Invalid above |
|-----------|----------------------------------|----------------|
| pm25 | 325.4 µg/m³ | 2000 |
| pm10 | 604 µg/m³ | 3000 |
| o3 | 0.200 ppm | 1 |
| co | 50.4 ppm | 100 |
| so2 | 1004 ppb | 5000 |
| no2 | 2049 ppb | 5000 |

---

## Weather rules

| Rule id | Severity | Condition |
|---------|----------|-----------|
| `missing_timestamp` | invalid | `observed_at` is null |
| `future_timestamp` | invalid / suspect | same clock-skew bands as AQ |
| `abnormal_value` | invalid | metric outside physical range |
| `duplicate_observation` | suspect | natural key duplicate (retained) |

### Weather physical ranges

| Field | Min | Max |
|-------|-----|-----|
| temperature_c | −90 | 60 |
| relative_humidity_pct | 0 | 100 |
| precipitation_mm | 0 | 500 |
| wind_speed_ms | 0 | 150 |
| wind_direction_deg | 0 | 360 |
| pressure_hpa | 800 | 1100 |

---

## Report / observability rules

Evaluated over a batch (Python report + `mart_data_quality_report`), not per-row
deletes:

| Check | Default | Meaning |
|-------|---------|---------|
| **Stale data** | latest obs &gt; **12 h** ago | `freshness.stale` / `is_stale` |
| **Sensor inactivity** | station silent &gt; **6 h** (longer than the expected **1 h** reporting interval — a single missed hour is not “inactive”) | listed under `sensor_activity` |
| **Sudden gaps / missing intervals** | gap &gt; **3 ×** expected 1 h interval | `missing_intervals` |
| **Delayed ingest** | `ingested_at − observed_at` &gt; **6 h** | `freshness.delayed_ingest_*` / rule `delayed_ingest` |

Missing concentrations are **never** treated as zero; null / absent values stay missing.

Pipeline failure modes (provider/broker/DB outages, rejects, duplicates): see
[`failure-recovery.md`](failure-recovery.md).

Report fields: record counts by class, duplicate counts, null counts, freshness,
sensor activity, min/max (and per-pollutant extremes), missing intervals, rule
hit counts.

---

## Python usage

```python
from datetime import UTC, datetime
from lahore_air_quality.quality import (
    AirQualityRecord,
    build_air_quality_report,
    classify_air_quality,
)

now = datetime(2026, 1, 1, 12, 0, tzinfo=UTC)
record = AirQualityRecord(
    station_id="PK-001",
    pollutant="pm25",
    value=42.0,
    unit="µg/m³",
    observed_at=datetime(2026, 1, 1, 11, 0, tzinfo=UTC),
)
result = classify_air_quality(record, now=now, has_weather_for_hour=True)
assert result.quality_class.value == "valid"

report = build_air_quality_report([record], weather_hours=[record.observed_at], now=now)
```

---

## dbt

```bash
dbt run --select path:models/quality
dbt test --select path:models/quality
```

| Model | Role |
|-------|------|
| `int_air_quality_classified` | Per-row flags + `quality_class` |
| `int_weather_classified` | Weather flags + `quality_class` |
| `mart_data_quality_report` | Single-row observability snapshot |

Singular test `assert_no_auto_delete_classified` ensures classified row counts
match staging (no silent drops).
