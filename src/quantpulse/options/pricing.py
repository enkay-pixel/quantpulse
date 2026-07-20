"""Black-Scholes pricing and Greeks for European options.

Implied volatility comes from the market (yfinance) so there is nothing to solve for —
given (spot, strike, time, rate, iv) these are closed-form. This module is pure and
deterministic; it is the tested core the rest of the options layer relies on.
"""

import math
from dataclasses import dataclass
from typing import Literal

from scipy.stats import norm

OptionType = Literal["call", "put"]

# Trading-day count used to annualize time-to-expiry from calendar days.
DAYS_PER_YEAR = 365.0


@dataclass(frozen=True)
class Greeks:
    price: float
    delta: float
    gamma: float
    theta: float  # per calendar day
    vega: float  # per 1 vol point (0.01)


def _d1_d2(spot: float, strike: float, t: float, r: float, iv: float) -> tuple[float, float]:
    vol_sqrt_t = iv * math.sqrt(t)
    d1 = (math.log(spot / strike) + (r + 0.5 * iv * iv) * t) / vol_sqrt_t
    d2 = d1 - vol_sqrt_t
    return d1, d2


def _intrinsic(spot: float, strike: float, kind: OptionType) -> float:
    return max(spot - strike, 0.0) if kind == "call" else max(strike - spot, 0.0)


def black_scholes(
    spot: float, strike: float, t_years: float, rate: float, iv: float, kind: OptionType
) -> Greeks:
    """Price + Greeks. Degenerate inputs (t<=0 or iv<=0) fall back to intrinsic value."""
    if t_years <= 0 or iv <= 0 or spot <= 0 or strike <= 0:
        return Greeks(
            price=_intrinsic(spot, strike, kind), delta=0.0, gamma=0.0, theta=0.0, vega=0.0
        )

    d1, d2 = _d1_d2(spot, strike, t_years, rate, iv)
    pdf_d1 = float(norm.pdf(d1))
    disc = math.exp(-rate * t_years)

    if kind == "call":
        price = spot * norm.cdf(d1) - strike * disc * norm.cdf(d2)
        delta = float(norm.cdf(d1))
        theta_year = -(spot * pdf_d1 * iv) / (
            2 * math.sqrt(t_years)
        ) - rate * strike * disc * float(norm.cdf(d2))
    else:
        price = strike * disc * norm.cdf(-d2) - spot * norm.cdf(-d1)
        delta = float(norm.cdf(d1) - 1.0)
        theta_year = -(spot * pdf_d1 * iv) / (
            2 * math.sqrt(t_years)
        ) + rate * strike * disc * float(norm.cdf(-d2))

    gamma = pdf_d1 / (spot * iv * math.sqrt(t_years))
    vega = spot * pdf_d1 * math.sqrt(t_years)

    return Greeks(
        price=float(price),
        delta=float(delta),
        gamma=float(gamma),
        theta=float(theta_year) / DAYS_PER_YEAR,  # per calendar day
        vega=float(vega) * 0.01,  # per 1 vol point
    )


def years_to_expiry(days: int) -> float:
    """Calendar days to expiry as a year fraction (floored just above zero)."""
    return max(days, 0) / DAYS_PER_YEAR
