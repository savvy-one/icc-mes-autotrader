"""Tests for StrategyEngine."""

from datetime import datetime, timedelta

import pytest
from icc.config import StrategyConfig
from icc.constants import FSMState
from icc.core.strategy import StrategyEngine
from icc.market.candle import Candle, CandleBuffer


def _build_uptrend_buffer(n: int = 30, base_price: float = 100.0) -> CandleBuffer:
    """Build a buffer with a clear uptrend: higher highs, higher lows, rising EMA."""
    buf = CandleBuffer(maxlen=200)
    base = datetime(2024, 1, 2, 9, 30)
    for i in range(n):
        price = base_price + i * 0.5
        # Last bar has higher volume to pass volume filter
        vol = 2000 if i == n - 1 else 1000
        buf.append(Candle(
            timestamp=base + timedelta(minutes=i),
            open=price - 0.25,
            high=price + 1.0,
            low=price - 0.5,
            close=price,
            volume=vol,
        ))
    return buf


def _build_downtrend_buffer(n: int = 30, base_price: float = 120.0) -> CandleBuffer:
    buf = CandleBuffer(maxlen=200)
    base = datetime(2024, 1, 2, 9, 30)
    for i in range(n):
        price = base_price - i * 0.5
        vol = 2000 if i == n - 1 else 1000
        buf.append(Candle(
            timestamp=base + timedelta(minutes=i),
            open=price + 0.25,
            high=price + 0.5,
            low=price - 1.0,
            close=price,
            volume=vol,
        ))
    return buf


class TestStrategyEngine:
    def test_insufficient_data(self):
        engine = StrategyEngine(StrategyConfig())
        buf = CandleBuffer(maxlen=200)
        buf.append(Candle(datetime.now(), 100, 101, 99, 100, 1000))
        signal = engine.evaluate(FSMState.FLAT, buf)
        assert signal.action == "none"

    def test_uptrend_indication(self):
        engine = StrategyEngine(StrategyConfig())
        buf = _build_uptrend_buffer()
        signal = engine.evaluate(FSMState.FLAT, buf)
        assert signal.action == "indication_up"

    def test_downtrend_indication(self):
        engine = StrategyEngine(StrategyConfig())
        buf = _build_downtrend_buffer()
        signal = engine.evaluate(FSMState.FLAT, buf)
        assert signal.action == "indication_down"

    def test_no_indication_on_flat_market(self):
        engine = StrategyEngine(StrategyConfig())
        buf = CandleBuffer(maxlen=200)
        base = datetime(2024, 1, 2, 9, 30)
        for i in range(30):
            buf.append(Candle(
                timestamp=base + timedelta(minutes=i),
                open=100.0, high=100.5, low=99.5, close=100.0, volume=500,
            ))
        signal = engine.evaluate(FSMState.FLAT, buf)
        assert signal.action == "none"

    def test_long_entry_signal_has_levels(self):
        engine = StrategyEngine(StrategyConfig())
        engine._impulse_high = 110.0
        engine._impulse_low = 105.0
        engine._correction_high = 109.0
        engine._correction_low = 106.0
        buf = _build_uptrend_buffer()
        signal = engine.evaluate(FSMState.CONTINUATION_UP, buf)
        assert signal.action == "enter_long"
        assert signal.entry_price is not None
        assert signal.stop_price is not None
        assert signal.target_price is not None
        assert signal.stop_price < signal.entry_price < signal.target_price
