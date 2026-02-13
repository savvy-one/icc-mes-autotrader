"""StrategyEngine — ICC signal generation."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from icc.config import StrategyConfig
from icc.constants import FSMState, MES_TICK_SIZE
from icc.core.indicators import (
    atr,
    ema_slope,
    higher_highs,
    higher_lows,
    is_in_fib_zone,
    lower_highs,
    lower_lows,
    volume_filter,
)
from icc.market.candle import CandleBuffer


@dataclass
class Signal:
    action: str  # "enter_long", "enter_short", "exit", "none"
    entry_price: float | None = None
    stop_price: float | None = None
    target_price: float | None = None
    reason: str = ""


class StrategyEngine:
    """Evaluates ICC conditions and produces signals. Does NOT manage state."""

    def __init__(self, config: StrategyConfig):
        self.config = config
        # Track correction context
        self._impulse_high: float | None = None
        self._impulse_low: float | None = None
        self._correction_high: float | None = None
        self._correction_low: float | None = None
        self._correction_bar_count: int = 0

    def reset(self) -> None:
        self._impulse_high = None
        self._impulse_low = None
        self._correction_high = None
        self._correction_low = None
        self._correction_bar_count = 0

    def evaluate(self, state: FSMState, buf: CandleBuffer) -> Signal:
        """Produce a signal given current FSM state and candle buffer."""
        if len(buf) < max(self.config.ema_period + 2, self.config.atr_period + 2):
            return Signal(action="none", reason="Insufficient data")

        if state == FSMState.FLAT:
            return self._check_indication(buf)
        elif state == FSMState.INDICATION_UP:
            return self._check_correction_up(buf)
        elif state == FSMState.INDICATION_DOWN:
            return self._check_correction_down(buf)
        elif state == FSMState.CORRECTION_UP:
            return self._check_continuation_up(buf)
        elif state == FSMState.CORRECTION_DOWN:
            return self._check_continuation_down(buf)
        elif state == FSMState.CONTINUATION_UP:
            return self._build_long_entry(buf)
        elif state == FSMState.CONTINUATION_DOWN:
            return self._build_short_entry(buf)
        else:
            return Signal(action="none")

    def _check_indication(self, buf: CandleBuffer) -> Signal:
        closes = buf.closes()
        highs = buf.highs()
        lows = buf.lows()
        volumes = buf.volumes()

        slope = ema_slope(closes, self.config.ema_period)

        # Check UP indication
        if (slope is not None and slope > 0
                and higher_highs(highs, count=2)
                and higher_lows(lows, count=2)
                and volume_filter(volumes, self.config.volume_avg_period)):
            self._impulse_high = max(highs[-3:])
            self._impulse_low = min(lows[-3:])
            return Signal(action="indication_up", reason="Bullish indication confirmed")

        # Check DOWN indication
        if (slope is not None and slope < 0
                and lower_lows(lows, count=2)
                and lower_highs(highs, count=2)
                and volume_filter(volumes, self.config.volume_avg_period)):
            self._impulse_high = max(highs[-3:])
            self._impulse_low = min(lows[-3:])
            return Signal(action="indication_down", reason="Bearish indication confirmed")

        return Signal(action="none", reason="No indication")

    def _check_correction_up(self, buf: CandleBuffer) -> Signal:
        if self._impulse_high is None or self._impulse_low is None:
            return Signal(action="none", reason="No impulse reference")

        candle = buf.last
        if candle is None:
            return Signal(action="none")

        if is_in_fib_zone(candle.close, self._impulse_low, self._impulse_high,
                          self.config.fib_min, self.config.fib_max):
            self._correction_high = candle.high
            self._correction_low = candle.low
            self._correction_bar_count = 0
            return Signal(action="correction_up", reason="Price in Fib retracement zone")

        return Signal(action="none", reason="Waiting for correction")

    def _check_correction_down(self, buf: CandleBuffer) -> Signal:
        if self._impulse_high is None or self._impulse_low is None:
            return Signal(action="none", reason="No impulse reference")

        candle = buf.last
        if candle is None:
            return Signal(action="none")

        if is_in_fib_zone(candle.close, self._impulse_low, self._impulse_high,
                          self.config.fib_min, self.config.fib_max):
            self._correction_high = candle.high
            self._correction_low = candle.low
            self._correction_bar_count = 0
            return Signal(action="correction_down", reason="Price in Fib retracement zone")

        return Signal(action="none", reason="Waiting for correction")

    def _check_continuation_up(self, buf: CandleBuffer) -> Signal:
        if self._correction_high is None:
            return Signal(action="none", reason="No correction reference")

        self._correction_bar_count += 1
        if self._correction_bar_count > self.config.correction_max_bars:
            return Signal(action="timeout", reason="Correction exceeded max bars")

        candle = buf.last
        if candle is None:
            return Signal(action="none")

        # Update correction extremes
        if candle.high > self._correction_high:
            self._correction_high = candle.high
        if candle.low < self._correction_low:
            self._correction_low = candle.low

        volumes = buf.volumes()
        if (candle.close > self._correction_high
                and volume_filter(volumes, self.config.continuation_volume_period)):
            return Signal(action="continuation_up",
                          reason="Break above correction high with volume")

        return Signal(action="none", reason="Waiting for continuation break")

    def _check_continuation_down(self, buf: CandleBuffer) -> Signal:
        if self._correction_low is None:
            return Signal(action="none", reason="No correction reference")

        self._correction_bar_count += 1
        if self._correction_bar_count > self.config.correction_max_bars:
            return Signal(action="timeout", reason="Correction exceeded max bars")

        candle = buf.last
        if candle is None:
            return Signal(action="none")

        if candle.high > self._correction_high:
            self._correction_high = candle.high
        if candle.low < self._correction_low:
            self._correction_low = candle.low

        volumes = buf.volumes()
        if (candle.close < self._correction_low
                and volume_filter(volumes, self.config.continuation_volume_period)):
            return Signal(action="continuation_down",
                          reason="Break below correction low with volume")

        return Signal(action="none", reason="Waiting for continuation break")

    def _build_long_entry(self, buf: CandleBuffer) -> Signal:
        if self._correction_high is None or self._correction_low is None:
            return Signal(action="none")

        closes = buf.closes()
        highs = buf.highs()
        lows = buf.lows()
        atr_vals = atr(highs, lows, closes, self.config.atr_period)
        if not atr_vals:
            return Signal(action="none", reason="ATR not available")

        current_atr = atr_vals[-1]
        entry = self._correction_high + MES_TICK_SIZE
        stop = self._correction_low - self.config.stop_atr_mult * current_atr
        target = entry + self.config.target_atr_mult * current_atr

        return Signal(
            action="enter_long",
            entry_price=entry,
            stop_price=stop,
            target_price=target,
            reason=f"Long entry: stop={stop:.2f}, target={target:.2f}, ATR={current_atr:.2f}",
        )

    def _build_short_entry(self, buf: CandleBuffer) -> Signal:
        if self._correction_high is None or self._correction_low is None:
            return Signal(action="none")

        closes = buf.closes()
        highs = buf.highs()
        lows = buf.lows()
        atr_vals = atr(highs, lows, closes, self.config.atr_period)
        if not atr_vals:
            return Signal(action="none", reason="ATR not available")

        current_atr = atr_vals[-1]
        entry = self._correction_low - MES_TICK_SIZE
        stop = self._correction_high + self.config.stop_atr_mult * current_atr
        target = entry - self.config.target_atr_mult * current_atr

        return Signal(
            action="enter_short",
            entry_price=entry,
            stop_price=stop,
            target_price=target,
            reason=f"Short entry: stop={stop:.2f}, target={target:.2f}, ATR={current_atr:.2f}",
        )
