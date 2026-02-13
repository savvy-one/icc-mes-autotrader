"""Tests for pure indicator functions."""

import pytest
from icc.core.indicators import (
    ema,
    ema_slope,
    atr,
    fibonacci_levels,
    is_in_fib_zone,
    higher_highs,
    higher_lows,
    lower_lows,
    lower_highs,
    volume_above_average,
)


class TestEMA:
    def test_ema_basic(self):
        values = list(range(1, 22))  # 1..21
        result = ema(values, 10)
        assert len(result) == 12  # 21 - 10 + 1
        assert result[0] == pytest.approx(5.5)  # SMA of 1..10

    def test_ema_too_short(self):
        assert ema([1, 2, 3], 10) == []

    def test_ema_slope_positive(self):
        values = list(range(1, 30))
        slope = ema_slope(values, 10)
        assert slope is not None
        assert slope > 0

    def test_ema_slope_negative(self):
        values = list(range(30, 0, -1))
        slope = ema_slope(values, 10)
        assert slope is not None
        assert slope < 0

    def test_ema_slope_insufficient_data(self):
        assert ema_slope([1, 2], 10) is None


class TestATR:
    def test_atr_basic(self):
        highs = [10.0 + i * 0.5 for i in range(20)]
        lows = [9.0 + i * 0.5 for i in range(20)]
        closes = [9.5 + i * 0.5 for i in range(20)]
        result = atr(highs, lows, closes, period=14)
        assert len(result) > 0
        assert all(v > 0 for v in result)

    def test_atr_too_short(self):
        assert atr([10], [9], [9.5], period=14) == []

    def test_atr_mismatched_lengths(self):
        assert atr([10, 11], [9], [9.5], period=1) == []


class TestFibonacci:
    def test_levels(self):
        levels = fibonacci_levels(100.0, 110.0)
        assert levels["0.0"] == pytest.approx(110.0)
        assert levels["1.0"] == pytest.approx(100.0)
        assert levels["0.382"] == pytest.approx(110.0 - 3.82)
        assert levels["0.618"] == pytest.approx(110.0 - 6.18)

    def test_in_fib_zone(self):
        # Price at 50% retracement should be in zone
        assert is_in_fib_zone(105.0, 100.0, 110.0)

    def test_outside_fib_zone(self):
        # Price at 80% retracement should be outside
        assert not is_in_fib_zone(102.0, 100.0, 110.0)

    def test_above_fib_zone(self):
        assert not is_in_fib_zone(109.0, 100.0, 110.0)


class TestHigherHighsLows:
    def test_higher_highs_true(self):
        assert higher_highs([10, 11, 12], count=2)

    def test_higher_highs_false(self):
        assert not higher_highs([10, 11, 10], count=2)

    def test_higher_lows_true(self):
        assert higher_lows([5, 6, 7], count=2)

    def test_lower_lows_true(self):
        assert lower_lows([10, 9, 8], count=2)

    def test_lower_highs_true(self):
        assert lower_highs([12, 11, 10], count=2)

    def test_insufficient_data(self):
        assert not higher_highs([10], count=2)


class TestVolumeFilter:
    def test_above_average(self):
        vols = [100] * 19 + [200]
        assert volume_above_average(vols, period=20)

    def test_below_average(self):
        vols = [200] * 19 + [100]
        assert not volume_above_average(vols, period=20)

    def test_insufficient_data(self):
        assert not volume_above_average([100, 200], period=20)
