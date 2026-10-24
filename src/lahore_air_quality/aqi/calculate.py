"""Deterministic US EPA AQI calculation.

See ``docs/aqi.md`` for methodology, units, averaging periods, and data
availability notes for this project.
"""

from __future__ import annotations

from collections.abc import Iterable
from decimal import ROUND_HALF_UP, Decimal, InvalidOperation

from lahore_air_quality.aqi.breakpoints import (
    POLLUTANT_SPECS,
    find_band,
    normalize_pollutant_code,
    supported_range,
    unit_matches,
)
from lahore_air_quality.aqi.categories import category_for_aqi
from lahore_air_quality.aqi.truncate import truncate_concentration
from lahore_air_quality.aqi.types import (
    AqiResult,
    AqiStatus,
    AveragingPeriod,
    PollutantReading,
    SubIndexResult,
)


def _as_decimal(value: Decimal | float | int) -> Decimal:
    if isinstance(value, Decimal):
        return value
    return Decimal(str(value))


def _normalize_averaging_period(
    value: AveragingPeriod | str | None,
) -> AveragingPeriod | None:
    if value is None:
        return None
    if isinstance(value, AveragingPeriod):
        return value
    cleaned = str(value).strip().lower().replace(" ", "").replace("_", "-")
    mapping = {
        "1-hour": AveragingPeriod.HOUR_1,
        "1h": AveragingPeriod.HOUR_1,
        "1hour": AveragingPeriod.HOUR_1,
        "8-hour": AveragingPeriod.HOUR_8,
        "8h": AveragingPeriod.HOUR_8,
        "8hour": AveragingPeriod.HOUR_8,
        "24-hour": AveragingPeriod.HOUR_24,
        "24h": AveragingPeriod.HOUR_24,
        "24hour": AveragingPeriod.HOUR_24,
    }
    return mapping.get(cleaned)


def _fail(
    *,
    status: AqiStatus,
    pollutant: str | None,
    unit: str | None,
    detail: str,
    truncated: Decimal | None = None,
) -> SubIndexResult:
    return SubIndexResult(
        status=status,
        pollutant=pollutant,
        aqi=None,
        category=None,
        concentration_truncated=truncated,
        unit=unit,
        detail=detail,
    )


def calculate_sub_index(
    pollutant: str,
    concentration: Decimal | float | int | None,
    unit: str,
    *,
    averaging_period: AveragingPeriod | str | None = None,
    require_averaging_period: bool = False,
) -> SubIndexResult:
    """Compute one pollutant AQI sub-index from a concentration.

    The concentration is assumed to already represent the EPA averaging period
    for that pollutant unless ``require_averaging_period`` is true, in which
    case a matching ``averaging_period`` must be supplied.

    Returns ``aqi=None`` (never invents a number) when input is missing,
    the unit is wrong, the pollutant is unsupported, or the truncated
    concentration falls outside the published AQI 0–500 breakpoint range.
    """
    code = normalize_pollutant_code(pollutant)
    if code is None:
        return _fail(
            status=AqiStatus.UNSUPPORTED_POLLUTANT,
            pollutant=pollutant.strip().lower() if pollutant else None,
            unit=unit,
            detail=f"pollutant {pollutant!r} is not in the EPA AQI table used by this project",
        )

    spec = POLLUTANT_SPECS[code]
    if not unit_matches(spec.unit, unit):
        return _fail(
            status=AqiStatus.INVALID_UNIT,
            pollutant=code,
            unit=unit,
            detail=(
                f"{code} requires unit {spec.unit!r} (EPA table); "
                f"got {unit!r}. No unit conversion is applied."
            ),
        )

    declared = _normalize_averaging_period(averaging_period)
    if require_averaging_period:
        if declared is None:
            return _fail(
                status=AqiStatus.AVERAGING_PERIOD_MISMATCH,
                pollutant=code,
                unit=spec.unit,
                detail=(
                    f"{code} requires averaging_period={spec.averaging_period.value!r} "
                    "when require_averaging_period=True"
                ),
            )
        if declared is not spec.averaging_period:
            return _fail(
                status=AqiStatus.AVERAGING_PERIOD_MISMATCH,
                pollutant=code,
                unit=spec.unit,
                detail=(f"{code} EPA AQI uses {spec.averaging_period.value}; got {declared.value}"),
            )

    if concentration is None:
        return _fail(
            status=AqiStatus.MISSING_VALUE,
            pollutant=code,
            unit=spec.unit,
            detail="concentration is missing",
        )

    try:
        conc = _as_decimal(concentration)
    except (InvalidOperation, ValueError, TypeError):
        return _fail(
            status=AqiStatus.INVALID_CONCENTRATION,
            pollutant=code,
            unit=spec.unit,
            detail=f"concentration {concentration!r} is not numeric",
        )

    if not conc.is_finite():
        return _fail(
            status=AqiStatus.INVALID_CONCENTRATION,
            pollutant=code,
            unit=spec.unit,
            detail="concentration must be finite",
        )

    low, high = supported_range(code)
    truncated = truncate_concentration(code, conc)

    if truncated < low:
        return _fail(
            status=AqiStatus.BELOW_SUPPORTED_RANGE,
            pollutant=code,
            unit=spec.unit,
            truncated=truncated,
            detail=(
                f"truncated concentration {truncated} is below the first EPA "
                f"breakpoint ({low} {spec.unit}) for {code}"
            ),
        )

    if truncated > high:
        return _fail(
            status=AqiStatus.ABOVE_SUPPORTED_RANGE,
            pollutant=code,
            unit=spec.unit,
            truncated=truncated,
            detail=(
                f"truncated concentration {truncated} is above the last EPA "
                f"breakpoint used for AQI≤500 ({high} {spec.unit}) for {code}"
            ),
        )

    band = find_band(code, truncated)
    if band is None:
        # Gap between published bands (should not occur for contiguous EPA tables).
        return _fail(
            status=AqiStatus.INSUFFICIENT_INPUT,
            pollutant=code,
            unit=spec.unit,
            truncated=truncated,
            detail=f"no EPA breakpoint band contains truncated concentration {truncated}",
        )

    # EPA equation 1:
    # Ip = ((IHi - ILo) / (BPHi - BPLo)) * (Cp - BPLo) + ILo
    bp_lo = band.concentration_low
    bp_hi = band.concentration_high
    i_lo = Decimal(band.aqi_low)
    i_hi = Decimal(band.aqi_high)
    if bp_hi == bp_lo:
        aqi_value = band.aqi_low
    else:
        aqi_dec = ((i_hi - i_lo) / (bp_hi - bp_lo)) * (truncated - bp_lo) + i_lo
        aqi_value = int(aqi_dec.quantize(Decimal("1"), rounding=ROUND_HALF_UP))

    return SubIndexResult(
        status=AqiStatus.OK,
        pollutant=code,
        aqi=aqi_value,
        category=category_for_aqi(aqi_value),
        concentration_truncated=truncated,
        unit=spec.unit,
        detail=None,
    )


def calculate_aqi(
    readings: Iterable[PollutantReading],
    *,
    require_averaging_period: bool = False,
) -> AqiResult:
    """Overall AQI = max of available valid sub-indices (EPA reporting rule).

    Missing pollutants are skipped. If **no** valid sub-index can be produced,
    returns ``status=INSUFFICIENT_INPUT`` and ``aqi=None`` — never a fabricated
    number.
    """
    sub_results: list[SubIndexResult] = []
    for reading in readings:
        sub_results.append(
            calculate_sub_index(
                reading.pollutant,
                reading.concentration,
                reading.unit,
                averaging_period=reading.averaging_period,
                require_averaging_period=require_averaging_period,
            )
        )

    ok_subs = [s for s in sub_results if s.ok and s.aqi is not None]
    if not ok_subs:
        return AqiResult(
            status=AqiStatus.INSUFFICIENT_INPUT,
            aqi=None,
            category=None,
            dominant_pollutant=None,
            sub_indices=tuple(sub_results),
            detail="no valid pollutant sub-index available",
        )

    dominant = max(ok_subs, key=lambda s: (s.aqi or -1, s.pollutant or ""))
    assert dominant.aqi is not None
    return AqiResult(
        status=AqiStatus.OK,
        aqi=dominant.aqi,
        category=dominant.category,
        dominant_pollutant=dominant.pollutant,
        sub_indices=tuple(sub_results),
        detail=None,
    )
