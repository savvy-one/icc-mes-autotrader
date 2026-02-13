"""Pure indicator functions: EMA, ATR, Fibonacci, HH/HL, volume filter."""

from __future__ import annotations


def ema(values: list[float], period: int) -> list[float]:
    """Compute EMA. Returns list same length as input (NaN-free after warm-up via SMA seed)."""
    if len(values) < period:
        return []
    result: list[float] = []
    k = 2.0 / (period + 1)
    # Seed with SMA
    sma = sum(values[:period]) / period
    result.append(sma)
    for v in values[period:]:
        sma = v * k + result[-1] * (1 - k)
        result.append(sma)
    return result


def ema_slope(values: list[float], period: int) -> float | None:
    """Return slope of last two EMA values. Positive = uptrend."""
    e = ema(values, period)
    if len(e) < 2:
        return None
    return e[-1] - e[-2]


def atr(highs: list[float], lows: list[float], closes: list[float],
        period: int = 14) -> list[float]:
    """Compute ATR using Wilder smoothing. Returns list of length len(highs) - 1 after warm-up."""
    if len(highs) < 2 or len(highs) != len(lows) or len(highs) != len(closes):
        return []

    trs: list[float] = []
    for i in range(1, len(highs)):
        tr = max(
            highs[i] - lows[i],
            abs(highs[i] - closes[i - 1]),
            abs(lows[i] - closes[i - 1]),
        )
        trs.append(tr)

    if len(trs) < period:
        return []

    result: list[float] = []
    first_atr = sum(trs[:period]) / period
    result.append(first_atr)
    for tr in trs[period:]:
        prev = result[-1]
        result.append((prev * (period - 1) + tr) / period)
    return result


def fibonacci_levels(swing_low: float, swing_high: float) -> dict[str, float]:
    """Compute Fibonacci retracement levels from a swing."""
    diff = swing_high - swing_low
    return {
        "0.0": swing_high,
        "0.236": swing_high - 0.236 * diff,
        "0.382": swing_high - 0.382 * diff,
        "0.5": swing_high - 0.5 * diff,
        "0.618": swing_high - 0.618 * diff,
        "0.786": swing_high - 0.786 * diff,
        "1.0": swing_low,
    }


def is_in_fib_zone(price: float, swing_low: float, swing_high: float,
                   fib_min: float = 0.382, fib_max: float = 0.618) -> bool:
    """Check if price is within the fib_min–fib_max retracement zone."""
    diff = swing_high - swing_low
    if diff <= 0:
        return False
    upper = swing_high - fib_min * diff
    lower = swing_high - fib_max * diff
    return lower <= price <= upper


def higher_highs(highs: list[float], count: int = 2) -> bool:
    """Check for `count` consecutive higher highs at the end of the series."""
    if len(highs) < count + 1:
        return False
    for i in range(len(highs) - count, len(highs)):
        if highs[i] <= highs[i - 1]:
            return False
    return True


def higher_lows(lows: list[float], count: int = 2) -> bool:
    """Check for `count` consecutive higher lows at the end of the series."""
    if len(lows) < count + 1:
        return False
    for i in range(len(lows) - count, len(lows)):
        if lows[i] <= lows[i - 1]:
            return False
    return True


def lower_lows(lows: list[float], count: int = 2) -> bool:
    """Check for `count` consecutive lower lows at the end of the series."""
    if len(lows) < count + 1:
        return False
    for i in range(len(lows) - count, len(lows)):
        if lows[i] >= lows[i - 1]:
            return False
    return True


def lower_highs(highs: list[float], count: int = 2) -> bool:
    """Check for `count` consecutive lower highs at the end of the series."""
    if len(highs) < count + 1:
        return False
    for i in range(len(highs) - count, len(highs)):
        if highs[i] >= highs[i - 1]:
            return False
    return True


def volume_above_average(volumes: list[int], period: int = 20) -> bool:
    """Check if last volume is above the `period`-bar average."""
    if len(volumes) < period:
        return False
    avg = sum(volumes[-period:]) / period
    return volumes[-1] > avg


def volume_filter(volumes: list[int], period: int = 20) -> bool:
    """Alias for volume_above_average."""
    return volume_above_average(volumes, period)
