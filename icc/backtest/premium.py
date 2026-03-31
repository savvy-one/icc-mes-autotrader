"""Synthetic option premium calculator for backtesting (Black-Scholes)."""

from __future__ import annotations

import math
from datetime import date


def _norm_cdf(x: float) -> float:
    """Standard normal CDF approximation (Abramowitz & Stegun)."""
    return 0.5 * (1.0 + math.erf(x / math.sqrt(2.0)))


def bs_premium(
    spot: float,
    strike: float,
    dte: float,
    vol: float,
    option_type: str = "CALL",
    risk_free: float = 0.05,
) -> float:
    """Black-Scholes option premium.

    Args:
        spot: Current underlying price.
        strike: Option strike price.
        dte: Days to expiration (fractional OK).
        vol: Annualized implied volatility (e.g. 0.20 = 20%).
        option_type: "CALL" or "PUT".
        risk_free: Annualized risk-free rate.

    Returns:
        Theoretical premium (per unit of underlying).
    """
    if dte <= 0:
        # Expired — intrinsic value only
        if option_type == "CALL":
            return max(0.0, spot - strike)
        return max(0.0, strike - spot)

    t = dte / 365.0
    sqrt_t = math.sqrt(t)

    d1 = (math.log(spot / strike) + (risk_free + 0.5 * vol ** 2) * t) / (vol * sqrt_t)
    d2 = d1 - vol * sqrt_t

    if option_type == "CALL":
        return spot * _norm_cdf(d1) - strike * math.exp(-risk_free * t) * _norm_cdf(d2)
    else:
        return strike * math.exp(-risk_free * t) * _norm_cdf(-d2) - spot * _norm_cdf(-d1)


def bs_delta(
    spot: float,
    strike: float,
    dte: float,
    vol: float,
    option_type: str = "CALL",
    risk_free: float = 0.05,
) -> float:
    """Black-Scholes delta."""
    if dte <= 0:
        if option_type == "CALL":
            return 1.0 if spot > strike else 0.0
        return -1.0 if spot < strike else 0.0

    t = dte / 365.0
    d1 = (math.log(spot / strike) + (risk_free + 0.5 * vol ** 2) * t) / (vol * math.sqrt(t))

    if option_type == "CALL":
        return _norm_cdf(d1)
    return _norm_cdf(d1) - 1.0


class SyntheticPremiumCalculator:
    """Computes synthetic option premiums for backtest replay.

    Usage::

        calc = SyntheticPremiumCalculator(vol=0.20, risk_free=0.05)
        premium = calc.premium(spot=5420, strike=5420, dte=0, option_type="CALL")
    """

    def __init__(self, vol: float = 0.20, risk_free: float = 0.05) -> None:
        self.vol = vol
        self.risk_free = risk_free

    def premium(
        self,
        spot: float,
        strike: float,
        dte: float,
        option_type: str = "CALL",
    ) -> float:
        return bs_premium(spot, strike, dte, self.vol, option_type, self.risk_free)

    def delta(
        self,
        spot: float,
        strike: float,
        dte: float,
        option_type: str = "CALL",
    ) -> float:
        return bs_delta(spot, strike, dte, self.vol, option_type, self.risk_free)

    def premium_from_contract(
        self,
        spot: float,
        strike: float,
        expiration: date,
        option_type: str,
        as_of: date | None = None,
    ) -> float:
        """Compute premium given a contract expiration date."""
        if as_of is None:
            as_of = date.today()
        dte = max(0, (expiration - as_of).days)
        return self.premium(spot, strike, float(dte), option_type)
