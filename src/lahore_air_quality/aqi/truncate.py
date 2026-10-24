"""EPA concentration truncation rules (before breakpoint lookup)."""

from __future__ import annotations

from decimal import ROUND_DOWN, Decimal

from lahore_air_quality.aqi.breakpoints import POLLUTANT_SPECS
from lahore_air_quality.aqi.types import PollutantCode


def truncate_concentration(pollutant: PollutantCode, concentration: Decimal) -> Decimal:
    """Truncate (not round) per EPA TAD rules for the pollutant."""
    decimals = POLLUTANT_SPECS[pollutant].truncate_decimals
    if decimals == 0:
        return concentration.to_integral_value(rounding=ROUND_DOWN)
    quant = Decimal("1").scaleb(-decimals)  # 10**-decimals
    return concentration.quantize(quant, rounding=ROUND_DOWN)
