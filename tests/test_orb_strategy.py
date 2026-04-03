"""Tests for ORB (Opening Range Breakout) strategy engine."""

from datetime import datetime, timedelta

import pytest

from icc.config import ORBConfig
from icc.constants import FSMState
from icc.core.fsm import ICCStateMachine
from icc.core.orb_strategy import ORBStrategyEngine
from icc.market.candle import Candle, CandleBuffer


def _make_candle(
    close: float,
    high: float | None = None,
    low: float | None = None,
    open_: float | None = None,
    volume: int = 500,
    minutes_offset: int = 0,
) -> Candle:
    """Create a test candle with sensible defaults."""
    if high is None:
        high = close + 1.0
    if low is None:
        low = close - 1.0
    if open_ is None:
        open_ = close
    return Candle(
        timestamp=datetime(2024, 1, 15, 9, 30) + timedelta(minutes=minutes_offset),
        open=open_,
        high=high,
        low=low,
        close=close,
        volume=volume,
    )


def _build_buffer(candles: list[Candle]) -> CandleBuffer:
    buf = CandleBuffer(maxlen=200)
    for c in candles:
        buf.append(c)
    return buf


class TestORBRangeBuilding:
    """Test the ORB_BUILDING phase."""

    def test_range_builds_over_n_candles(self):
        """Range should accumulate high/low over range_minutes candles."""
        config = ORBConfig(range_minutes=3)
        engine = ORBStrategyEngine(config)
        buf = CandleBuffer(maxlen=200)

        # First candle triggers orb_start
        c1 = _make_candle(5200, high=5205, low=5195, minutes_offset=0)
        buf.append(c1)
        sig = engine.evaluate(FSMState.FLAT, buf)
        assert sig.action == "orb_start"

        # Build range — candle 2
        c2 = _make_candle(5210, high=5215, low=5198, minutes_offset=1)
        buf.append(c2)
        sig = engine.evaluate(FSMState.ORB_BUILDING, buf)
        assert sig.action == "none"

        # Build range — candle 3 completes the range
        c3 = _make_candle(5205, high=5212, low=5190, minutes_offset=2)
        buf.append(c3)
        sig = engine.evaluate(FSMState.ORB_BUILDING, buf)
        assert sig.action == "range_set"

        # Verify range extremes
        assert engine._range_high == 5215  # max of all highs
        assert engine._range_low == 5190   # min of all lows

    def test_range_set_signal_after_window(self):
        """range_set should fire exactly when range_minutes candles are accumulated."""
        config = ORBConfig(range_minutes=5)
        engine = ORBStrategyEngine(config)
        buf = CandleBuffer(maxlen=200)

        # Trigger orb_start
        buf.append(_make_candle(5200, minutes_offset=0))
        engine.evaluate(FSMState.FLAT, buf)

        # Feed 4 more candles (total 5 = range_minutes)
        for i in range(1, 5):
            buf.append(_make_candle(5200 + i, minutes_offset=i))
            sig = engine.evaluate(FSMState.ORB_BUILDING, buf)
            if i < 4:
                assert sig.action == "none"
            else:
                assert sig.action == "range_set"


class TestORBBreakout:
    """Test the ORB_ARMED phase — breakout/breakdown detection."""

    def _armed_engine(self, range_high=5210.0, range_low=5190.0, config=None):
        """Create an engine pre-loaded with a known range."""
        if config is None:
            config = ORBConfig(range_minutes=3, target_multiplier=1.5, max_wait_minutes=60, confirmation_bars=1)
        engine = ORBStrategyEngine(config)
        engine._range_high = range_high
        engine._range_low = range_low
        engine._range_candle_count = 3
        engine._range_volume_sum = 1500.0
        engine._armed_bar_count = 0
        engine._orb_started = True
        return engine

    def test_breakout_above_range_high_long_signal(self):
        """Close above range_high should produce enter_long after confirmation."""
        config = ORBConfig(range_minutes=3, target_multiplier=1.5, max_wait_minutes=60, confirmation_bars=1)
        engine = self._armed_engine(range_high=5210, range_low=5190, config=config)
        buf = CandleBuffer(maxlen=200)
        buf.append(_make_candle(5215, high=5218, low=5208))

        sig = engine.evaluate(FSMState.ORB_ARMED, buf)
        assert sig.action == "enter_long"
        assert sig.entry_price == 5215
        assert sig.stop_price == 5190  # opposite side (default)
        assert sig.target_price == 5215 + (5210 - 5190) * 1.5  # entry + range * mult

    def test_breakdown_below_range_low_short_signal(self):
        """Close below range_low should produce enter_short after confirmation."""
        config = ORBConfig(range_minutes=3, target_multiplier=1.5, max_wait_minutes=60, confirmation_bars=1)
        engine = self._armed_engine(range_high=5210, range_low=5190, config=config)
        buf = CandleBuffer(maxlen=200)
        buf.append(_make_candle(5185, high=5195, low=5182))

        sig = engine.evaluate(FSMState.ORB_ARMED, buf)
        assert sig.action == "enter_short"
        assert sig.entry_price == 5185
        assert sig.stop_price == 5210  # opposite side
        assert sig.target_price == 5185 - (5210 - 5190) * 1.5

    def test_no_breakout_within_range(self):
        """Close within range should produce no signal."""
        engine = self._armed_engine(range_high=5210, range_low=5190)
        buf = CandleBuffer(maxlen=200)
        buf.append(_make_candle(5200, high=5208, low=5192))

        sig = engine.evaluate(FSMState.ORB_ARMED, buf)
        assert sig.action == "none"

    def test_range_expired_rerange(self):
        """Should re-range after max_wait_minutes when re_range_on_expiry is True."""
        config = ORBConfig(range_minutes=3, max_wait_minutes=5, re_range_on_expiry=True)
        engine = self._armed_engine(config=config)
        buf = CandleBuffer(maxlen=200)

        for i in range(6):
            buf.append(_make_candle(5200, high=5205, low=5195, minutes_offset=i))
            sig = engine.evaluate(FSMState.ORB_ARMED, buf)
            if i < 5:
                assert sig.action == "none"
            else:
                assert sig.action == "range_expired_rerange"

    def test_range_expired_no_rerange(self):
        """Should expire without re-range when disabled."""
        config = ORBConfig(range_minutes=3, max_wait_minutes=5, re_range_on_expiry=False)
        engine = self._armed_engine(config=config)
        buf = CandleBuffer(maxlen=200)

        for i in range(6):
            buf.append(_make_candle(5200, high=5205, low=5195, minutes_offset=i))
            sig = engine.evaluate(FSMState.ORB_ARMED, buf)
            if i < 5:
                assert sig.action == "none"
            else:
                assert sig.action == "range_expired"

    def test_max_ranges_cap(self):
        """Should stop re-ranging after max_ranges_per_session."""
        config = ORBConfig(range_minutes=3, max_wait_minutes=5, re_range_on_expiry=True, max_ranges_per_session=2)
        engine = self._armed_engine(config=config)
        engine._ranges_built = 2
        buf = CandleBuffer(maxlen=200)

        for i in range(6):
            buf.append(_make_candle(5200, high=5205, low=5195, minutes_offset=i))
            sig = engine.evaluate(FSMState.ORB_ARMED, buf)
        assert sig.action == "range_expired"

    def test_stop_at_midpoint(self):
        """Stop mode 'midpoint' should set stop at range midpoint."""
        config = ORBConfig(range_minutes=3, stop_mode="midpoint", target_multiplier=1.5, confirmation_bars=1)
        engine = self._armed_engine(range_high=5210, range_low=5190, config=config)
        buf = CandleBuffer(maxlen=200)
        buf.append(_make_candle(5215, high=5218, low=5208))

        sig = engine.evaluate(FSMState.ORB_ARMED, buf)
        assert sig.action == "enter_long"
        assert sig.stop_price == 5200  # midpoint of 5190-5210

    def test_target_uses_multiplier(self):
        """Target should be entry + range_height * multiplier."""
        config = ORBConfig(range_minutes=3, target_multiplier=2.0, confirmation_bars=1)
        engine = self._armed_engine(range_high=5210, range_low=5190, config=config)
        buf = CandleBuffer(maxlen=200)
        buf.append(_make_candle(5215, high=5218, low=5208))

        sig = engine.evaluate(FSMState.ORB_ARMED, buf)
        range_height = 5210 - 5190  # 20
        assert sig.target_price == 5215 + range_height * 2.0  # 5255

    def test_volume_confirmation_blocks_low_volume(self):
        """Volume confirmation should block breakout on low volume."""
        config = ORBConfig(
            range_minutes=3, volume_confirmation=True, volume_threshold_pct=120, confirmation_bars=1,
        )
        engine = self._armed_engine(config=config)
        # avg volume = 1500/3 = 500; threshold = 500 * 1.2 = 600
        buf = CandleBuffer(maxlen=200)
        buf.append(_make_candle(5215, high=5218, low=5208, volume=400))  # below threshold

        sig = engine.evaluate(FSMState.ORB_ARMED, buf)
        assert sig.action == "none"

    def test_volume_confirmation_passes_high_volume(self):
        """Volume confirmation should allow breakout on high volume."""
        config = ORBConfig(
            range_minutes=3, volume_confirmation=True, volume_threshold_pct=120, confirmation_bars=1,
        )
        engine = self._armed_engine(config=config)
        buf = CandleBuffer(maxlen=200)
        buf.append(_make_candle(5215, high=5218, low=5208, volume=700))  # above threshold

        sig = engine.evaluate(FSMState.ORB_ARMED, buf)
        assert sig.action == "enter_long"


class TestORBReset:
    """Test reset vs full_reset behavior."""

    def test_reset_preserves_session_flags(self):
        """reset() preserves _orb_started and _trade_taken to prevent restart."""
        engine = ORBStrategyEngine(ORBConfig())
        engine._range_high = 5210
        engine._range_low = 5190
        engine._range_candle_count = 15
        engine._range_volume_sum = 7500
        engine._armed_bar_count = 5
        engine._orb_started = True
        engine._trade_taken = True

        engine.reset()

        # Session flags survive reset
        assert engine._orb_started is True
        assert engine._trade_taken is True
        # Per-trade state is cleared
        assert engine._armed_bar_count == 0

    def test_full_reset_clears_everything(self):
        """full_reset() clears all state for a new session."""
        engine = ORBStrategyEngine(ORBConfig())
        engine._range_high = 5210
        engine._range_low = 5190
        engine._range_candle_count = 15
        engine._range_volume_sum = 7500
        engine._armed_bar_count = 5
        engine._orb_started = True
        engine._trade_taken = True

        engine.full_reset()

        assert engine._range_high is None
        assert engine._range_low is None
        assert engine._range_candle_count == 0
        assert engine._range_volume_sum == 0.0
        assert engine._armed_bar_count == 0
        assert engine._orb_started is False
        assert engine._trade_taken is False

    def test_no_reentry_after_trade(self):
        """After a trade is taken, ORB should not restart (reentry_allowed=False)."""
        config = ORBConfig(reentry_allowed=False)
        engine = ORBStrategyEngine(config)
        engine._orb_started = True
        engine._trade_taken = True

        buf = CandleBuffer(maxlen=200)
        buf.append(_make_candle(5200))

        sig = engine.evaluate(FSMState.FLAT, buf)
        assert sig.action == "none"
        assert "no re-entry" in sig.reason

    def test_reentry_allowed_restarts_orb(self):
        """With reentry_allowed=True, ORB should restart after a trade."""
        config = ORBConfig(reentry_allowed=True)
        engine = ORBStrategyEngine(config)
        engine._trade_taken = True
        engine._orb_started = False  # cleared for re-entry

        buf = CandleBuffer(maxlen=200)
        buf.append(_make_candle(5200))

        sig = engine.evaluate(FSMState.FLAT, buf)
        assert sig.action == "orb_start"


class TestORBFSMTransitions:
    """Test FSM integration with ORB states."""

    def test_flat_to_orb_building(self):
        fsm = ICCStateMachine()
        assert fsm.state == FSMState.FLAT
        fsm.transition("orb_start")
        assert fsm.state == FSMState.ORB_BUILDING

    def test_orb_building_to_armed(self):
        fsm = ICCStateMachine()
        fsm.transition("orb_start")
        fsm.transition("range_set")
        assert fsm.state == FSMState.ORB_ARMED

    def test_orb_armed_to_in_trade(self):
        fsm = ICCStateMachine()
        fsm.transition("orb_start")
        fsm.transition("range_set")
        fsm.transition("enter_long")
        assert fsm.state == FSMState.IN_TRADE_UP

    def test_orb_armed_to_in_trade_short(self):
        fsm = ICCStateMachine()
        fsm.transition("orb_start")
        fsm.transition("range_set")
        fsm.transition("enter_short")
        assert fsm.state == FSMState.IN_TRADE_DOWN

    def test_orb_armed_range_expired_to_flat(self):
        fsm = ICCStateMachine()
        fsm.transition("orb_start")
        fsm.transition("range_set")
        fsm.transition("range_expired")
        assert fsm.state == FSMState.FLAT

    def test_full_cycle_flat_to_exit_to_flat(self):
        """FLAT → ORB_BUILDING → ORB_ARMED → IN_TRADE_UP → EXIT → FLAT"""
        fsm = ICCStateMachine()
        fsm.transition("orb_start")
        assert fsm.state == FSMState.ORB_BUILDING
        fsm.transition("range_set")
        assert fsm.state == FSMState.ORB_ARMED
        fsm.transition("enter_long")
        assert fsm.state == FSMState.IN_TRADE_UP
        fsm.transition("target_hit")
        assert fsm.state == FSMState.EXIT
        fsm.transition("reset")
        assert fsm.state == FSMState.FLAT


class TestORBConfigValidation:
    """Test ORBConfig defaults and values."""

    def test_default_config(self):
        config = ORBConfig()
        assert config.range_minutes == 15
        assert config.target_multiplier == 1.5
        assert config.stop_mode == "opposite"
        assert config.volume_confirmation is False
        assert config.volume_threshold_pct == 120.0
        assert config.max_wait_minutes == 120
        assert config.reentry_allowed is True
        assert config.re_range_on_expiry is True
        assert config.max_ranges_per_session == 3

    def test_custom_config(self):
        config = ORBConfig(
            range_minutes=10,
            target_multiplier=2.0,
            stop_mode="midpoint",
            volume_confirmation=True,
        )
        assert config.range_minutes == 10
        assert config.target_multiplier == 2.0
        assert config.stop_mode == "midpoint"
        assert config.volume_confirmation is True
