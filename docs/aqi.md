# AQI methodology

## Standard used

This project uses the **United States EPA Air Quality Index (AQI)** as published in:

- [40 CFR Part 58, Appendix G](https://www.ecfr.gov/current/title-40/chapter-I/subchapter-C/part-58/appendix-Appendix%20G%20to%20Part%2058) — Uniform Air Quality Index (AQI) and Daily Reporting  
- EPA **February 2024** update to PM2.5 AQI breakpoints (effective **6 May 2024**)  
- AirNow *Technical Assistance Document for the Reporting of Daily Air Quality* (TAD)

**Why EPA / AirNow for Lahore?**  
Primary OpenAQ coverage used in development (e.g. US Consulate Lahore) is an **AirNow** feed. AirNow reports the US EPA AQI. Using EPA breakpoints keeps the platform consistent with the dominant upstream reporting system for those monitors. This is **not** a claim that EPA AQI is Pakistan’s official national index; it is the documented choice for this portfolio pipeline given available data.

Breakpoints are **copied from EPA tables**. They are never invented in application code.

Implementation:

| Layer | Location |
|-------|----------|
| Pure Python (unit-tested source of truth) | `src/lahore_air_quality/aqi/` |
| dbt seed (same numbers) | `dbt/lahore_air_quality/seeds/aqi_breakpoints.csv` |
| dbt models | `int_air_quality_aqi_subindex`, `mart_lahore_aqi` |

## Pollutants and units in *this* project

### What the pipeline can store

| Canonical code | Typical OpenAQ names | Unit required for EPA AQI | Present in Lahore fixtures / common AirNow feeds |
|----------------|----------------------|---------------------------|--------------------------------------------------|
| `pm25` | `pm25`, `pm2.5` | **µg/m³** | **Yes** (primary) |
| `pm10` | `pm10` | **µg/m³** | Possible if OpenAQ exposes it |
| `o3` | `o3`, ozone | **ppm** | Possible; OpenAQ often uses µg/m³ — **not converted** |
| `co` | `co` | **ppm** | Possible |
| `so2` | `so2` | **ppb** | Possible |
| `no2` | `no2` | **ppb** | Possible |

Raw observations keep the **source unit** from OpenAQ. The AQI layer **does not invent unit conversions**. If the unit does not match the EPA table unit for that pollutant, **no AQI is calculated** for that reading.

### Truncation (EPA TAD)

Before breakpoint lookup, concentrations are **truncated** (not rounded):

| Pollutant | Truncation |
|-----------|------------|
| PM2.5 | 1 decimal place |
| PM10 | integer |
| O3 | 3 decimal places |
| CO | 1 decimal place |
| SO2 | integer |
| NO2 | integer |

## Averaging periods (EPA)

Official EPA AQI for each pollutant is defined on a specific average:

| Pollutant | Averaging period for published AQI |
|-----------|--------------------------------------|
| PM2.5, PM10 | **24-hour** |
| O3 (primary table used here) | **8-hour** |
| CO | **8-hour** |
| SO2, NO2 | **1-hour** |

The Python API treats the supplied concentration as **already averaged** for that period. Callers that need a hard check can set `require_averaging_period=True` and pass `averaging_period`.

dbt `mart_lahore_aqi` documents two related products:

1. **Operational hourly AQI** — sub-index from the hour’s mean concentration (useful for near-real-time dashboards; **not** a substitute for the EPA 24-hour PM AQI).  
2. **`pm25_rolling_24h_avg`** — rolling 24-hour mean of hourly PM2.5 for closer alignment with EPA PM practice.

## Equation

For truncated concentration \(C_p\) falling between breakpoints \(BP_{Lo}\) and \(BP_{Hi}\) with corresponding index bounds \(I_{Lo}\) and \(I_{Hi}\):

\[
I_p = \frac{I_{Hi} - I_{Lo}}{BP_{Hi} - BP_{Lo}}(C_p - BP_{Lo}) + I_{Lo}
\]

Round \(I_p\) to the nearest integer.

**Overall AQI** = maximum of available valid pollutant sub-indices (EPA reporting rule).

## Missing and out-of-range handling

| Situation | Result |
|-----------|--------|
| Missing concentration | No sub-index (`missing_value`) |
| Unsupported pollutant | No sub-index (`unsupported_pollutant`) |
| Wrong unit | No sub-index (`invalid_unit`) — no silent conversion |
| Truncated value **below** first breakpoint | No sub-index (`below_supported_range`) |
| Truncated value **above** last breakpoint for AQI ≤ 500 | No sub-index (`above_supported_range`) — **AQI > 500 is not invented** |
| No valid sub-index among inputs | Overall AQI is **not** calculated (`insufficient_input`) |

Supported concentration ranges end at the EPA Hazardous band used for **AQI 500** (e.g. PM2.5 ≤ 325.4 µg/m³). Values above that are reported as out of supported range rather than extrapolating unpublished breakpoints.

## Categories

| AQI | Category |
|-----|----------|
| 0–50 | Good |
| 51–100 | Moderate |
| 101–150 | Unhealthy for Sensitive Groups |
| 151–200 | Unhealthy |
| 201–300 | Very Unhealthy |
| 301–500 | Hazardous |

## Python usage

```python
from lahore_air_quality.aqi import (
    PollutantReading,
    calculate_aqi,
    calculate_sub_index,
)
from lahore_air_quality.aqi.types import AveragingPeriod

sub = calculate_sub_index("pm25", 87.5, "µg/m³")
assert sub.ok
assert sub.aqi is not None

overall = calculate_aqi(
    [
        PollutantReading("pm25", 87.5, "µg/m³", AveragingPeriod.HOUR_24),
        PollutantReading("pm10", None, "µg/m³"),  # skipped
    ]
)
```

## Keeping dbt in sync

`tests/aqi/test_breakpoints_seed_sync.py` asserts that
`dbt/lahore_air_quality/seeds/aqi_breakpoints.csv` matches
`lahore_air_quality.aqi.breakpoints`. Update **Python first**, then the seed.
