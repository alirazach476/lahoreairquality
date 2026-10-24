"""US EPA AQI breakpoints (published tables — not invented).

Source
------
40 CFR Part 58, Appendix G, Table 2 (AQI breakpoints), including the
February 2024 PM2.5 AQI breakpoint update (effective May 6, 2024).

Cross-check:
- https://www.ecfr.gov/current/title-40/chapter-I/subchapter-C/part-58/appendix-Appendix%20G%20to%20Part%2058
- EPA “Final Updates to the Air Quality Index (AQI) for Particulate Matter” (Feb 2024)
- AirNow Technical Assistance Document for the Reporting of Daily Air Quality

This module supports **AQI 0–500 only**. Concentrations above the Hazardous
band high breakpoint for AQI 500 are treated as out of supported range
(no value is invented for AQI > 500).
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from typing import Final

from lahore_air_quality.aqi.types import AveragingPeriod, PollutantCode


@dataclass(frozen=True, slots=True)
class BreakpointBand:
    """One EPA concentration → AQI band for a pollutant."""

    pollutant: PollutantCode
    unit: str
    concentration_low: Decimal
    concentration_high: Decimal
    aqi_low: int
    aqi_high: int
    category: str


@dataclass(frozen=True, slots=True)
class PollutantSpec:
    """Unit, truncation, and averaging metadata for an EPA AQI pollutant."""

    code: PollutantCode
    unit: str
    averaging_period: AveragingPeriod
    truncate_decimals: int
    aliases: frozenset[str]


# ---------------------------------------------------------------------------
# Published EPA breakpoint table (AQI 0–500)
# ---------------------------------------------------------------------------

_EPA_BREAKPOINTS: Final[tuple[BreakpointBand, ...]] = (
    # PM2.5 (µg/m³), 24-hour — 2024 breakpoints
    BreakpointBand("pm25", "µg/m³", Decimal("0.0"), Decimal("9.0"), 0, 50, "Good"),
    BreakpointBand("pm25", "µg/m³", Decimal("9.1"), Decimal("35.4"), 51, 100, "Moderate"),
    BreakpointBand(
        "pm25",
        "µg/m³",
        Decimal("35.5"),
        Decimal("55.4"),
        101,
        150,
        "Unhealthy for Sensitive Groups",
    ),
    BreakpointBand("pm25", "µg/m³", Decimal("55.5"), Decimal("125.4"), 151, 200, "Unhealthy"),
    BreakpointBand("pm25", "µg/m³", Decimal("125.5"), Decimal("225.4"), 201, 300, "Very Unhealthy"),
    BreakpointBand("pm25", "µg/m³", Decimal("225.5"), Decimal("325.4"), 301, 500, "Hazardous"),
    # PM10 (µg/m³), 24-hour
    BreakpointBand("pm10", "µg/m³", Decimal("0"), Decimal("54"), 0, 50, "Good"),
    BreakpointBand("pm10", "µg/m³", Decimal("55"), Decimal("154"), 51, 100, "Moderate"),
    BreakpointBand(
        "pm10", "µg/m³", Decimal("155"), Decimal("254"), 101, 150, "Unhealthy for Sensitive Groups"
    ),
    BreakpointBand("pm10", "µg/m³", Decimal("255"), Decimal("354"), 151, 200, "Unhealthy"),
    BreakpointBand("pm10", "µg/m³", Decimal("355"), Decimal("424"), 201, 300, "Very Unhealthy"),
    BreakpointBand("pm10", "µg/m³", Decimal("425"), Decimal("604"), 301, 500, "Hazardous"),
    # O3 (ppm), 8-hour (1-hour O3 bands for AQI>300 are not used in this project)
    BreakpointBand("o3", "ppm", Decimal("0.000"), Decimal("0.054"), 0, 50, "Good"),
    BreakpointBand("o3", "ppm", Decimal("0.055"), Decimal("0.070"), 51, 100, "Moderate"),
    BreakpointBand(
        "o3", "ppm", Decimal("0.071"), Decimal("0.085"), 101, 150, "Unhealthy for Sensitive Groups"
    ),
    BreakpointBand("o3", "ppm", Decimal("0.086"), Decimal("0.105"), 151, 200, "Unhealthy"),
    BreakpointBand("o3", "ppm", Decimal("0.106"), Decimal("0.200"), 201, 300, "Very Unhealthy"),
    # CO (ppm), 8-hour
    BreakpointBand("co", "ppm", Decimal("0.0"), Decimal("4.4"), 0, 50, "Good"),
    BreakpointBand("co", "ppm", Decimal("4.5"), Decimal("9.4"), 51, 100, "Moderate"),
    BreakpointBand(
        "co", "ppm", Decimal("9.5"), Decimal("12.4"), 101, 150, "Unhealthy for Sensitive Groups"
    ),
    BreakpointBand("co", "ppm", Decimal("12.5"), Decimal("15.4"), 151, 200, "Unhealthy"),
    BreakpointBand("co", "ppm", Decimal("15.5"), Decimal("30.4"), 201, 300, "Very Unhealthy"),
    BreakpointBand("co", "ppm", Decimal("30.5"), Decimal("50.4"), 301, 500, "Hazardous"),
    # SO2 (ppb), 1-hour
    BreakpointBand("so2", "ppb", Decimal("0"), Decimal("35"), 0, 50, "Good"),
    BreakpointBand("so2", "ppb", Decimal("36"), Decimal("75"), 51, 100, "Moderate"),
    BreakpointBand(
        "so2", "ppb", Decimal("76"), Decimal("185"), 101, 150, "Unhealthy for Sensitive Groups"
    ),
    BreakpointBand("so2", "ppb", Decimal("186"), Decimal("304"), 151, 200, "Unhealthy"),
    BreakpointBand("so2", "ppb", Decimal("305"), Decimal("604"), 201, 300, "Very Unhealthy"),
    BreakpointBand("so2", "ppb", Decimal("605"), Decimal("1004"), 301, 500, "Hazardous"),
    # NO2 (ppb), 1-hour
    BreakpointBand("no2", "ppb", Decimal("0"), Decimal("53"), 0, 50, "Good"),
    BreakpointBand("no2", "ppb", Decimal("54"), Decimal("100"), 51, 100, "Moderate"),
    BreakpointBand(
        "no2", "ppb", Decimal("101"), Decimal("360"), 101, 150, "Unhealthy for Sensitive Groups"
    ),
    BreakpointBand("no2", "ppb", Decimal("361"), Decimal("649"), 151, 200, "Unhealthy"),
    BreakpointBand("no2", "ppb", Decimal("650"), Decimal("1249"), 201, 300, "Very Unhealthy"),
    BreakpointBand("no2", "ppb", Decimal("1250"), Decimal("2049"), 301, 500, "Hazardous"),
)


POLLUTANT_SPECS: Final[dict[PollutantCode, PollutantSpec]] = {
    "pm25": PollutantSpec(
        code="pm25",
        unit="µg/m³",
        averaging_period=AveragingPeriod.HOUR_24,
        truncate_decimals=1,
        aliases=frozenset({"pm25", "pm2.5", "pm_2_5", "pm2_5"}),
    ),
    "pm10": PollutantSpec(
        code="pm10",
        unit="µg/m³",
        averaging_period=AveragingPeriod.HOUR_24,
        truncate_decimals=0,
        aliases=frozenset({"pm10", "pm10.0", "pm_10"}),
    ),
    "o3": PollutantSpec(
        code="o3",
        unit="ppm",
        averaging_period=AveragingPeriod.HOUR_8,
        truncate_decimals=3,
        aliases=frozenset({"o3", "ozone", "o_3"}),
    ),
    "co": PollutantSpec(
        code="co",
        unit="ppm",
        averaging_period=AveragingPeriod.HOUR_8,
        truncate_decimals=1,
        aliases=frozenset({"co", "carbonmonoxide", "carbon_monoxide"}),
    ),
    "so2": PollutantSpec(
        code="so2",
        unit="ppb",
        averaging_period=AveragingPeriod.HOUR_1,
        truncate_decimals=0,
        aliases=frozenset({"so2", "sulfurdioxide", "sulphurdioxide", "so_2"}),
    ),
    "no2": PollutantSpec(
        code="no2",
        unit="ppb",
        averaging_period=AveragingPeriod.HOUR_1,
        truncate_decimals=0,
        aliases=frozenset({"no2", "nitrogendioxide", "no_2"}),
    ),
}

# Units accepted as spelling variants of the EPA table unit (no conversion).
_UNIT_ALIASES: Final[dict[str, frozenset[str]]] = {
    "µg/m³": frozenset({"µg/m³", "ug/m³", "ug/m3", "µg/m3"}),
    "ppm": frozenset({"ppm"}),
    "ppb": frozenset({"ppb"}),
}


def all_breakpoint_bands() -> tuple[BreakpointBand, ...]:
    """Return the full published breakpoint table used by this project."""
    return _EPA_BREAKPOINTS


def bands_for(pollutant: PollutantCode) -> tuple[BreakpointBand, ...]:
    return tuple(b for b in _EPA_BREAKPOINTS if b.pollutant == pollutant)


def supported_range(pollutant: PollutantCode) -> tuple[Decimal, Decimal]:
    """Inclusive concentration range covered by AQI 0–500 for ``pollutant``."""
    bands = bands_for(pollutant)
    return bands[0].concentration_low, bands[-1].concentration_high


def normalize_pollutant_code(raw: str) -> PollutantCode | None:
    cleaned = raw.strip().lower().replace(" ", "").replace("-", "_")
    for code, spec in POLLUTANT_SPECS.items():
        if cleaned in spec.aliases or cleaned == code:
            return code
    return None


def unit_matches(expected: str, actual: str) -> bool:
    aliases = _UNIT_ALIASES.get(expected, frozenset({expected.lower()}))
    return actual.strip().lower() in {a.lower() for a in aliases} or (actual.strip() == expected)


def find_band(pollutant: PollutantCode, truncated: Decimal) -> BreakpointBand | None:
    """Return the EPA band containing ``truncated``, or None if out of range."""
    for band in bands_for(pollutant):
        if band.concentration_low <= truncated <= band.concentration_high:
            return band
    return None
