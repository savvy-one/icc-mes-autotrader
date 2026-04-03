"""ORBStrategyEngine — Opening Range Breakout signal generation."""

from __future__ import annotations

import logging
from typing import Optional

from icc.config import ORBConfig
from icc.constants import FSMState
from icc.core.strategy import Signal
from icc.market.candle import CandleBuffer

logger = logging.getLogger(__name__)


class ORBStrategyEngine:
    """Evaluates Opening Range Breakout conditions and produces signals.

    Phase 1 (ORB_BUILDING): Accumulate high/low of the first N candles.
    Phase 2 (ORB_ARMED): Watch for close above range_high (long) or below range_low (short).
    """

    def __init__(self, config: ORBConfig) -> None:
        self.config = config
        self._range_high: Optional[float] = None
        self._range_low: Optional[float] = None
        self._range_candle_count: int = 0
        self._range_volume_sum: float = 0.0
        self._armed_bar_count: int = 0
        self._orb_started: bool = False
        self._trade_taken: bool = False  # survives reset — one ORB per session
        self._breakout_streak: int = 0  # consecutive bars beyond range (for confirmation)
        self._breakout_direction: str = ""  # "long" or "short"
        self._ranges_built: int = 0  # how many ranges built this session

    @property
    def range_height(self) -> float | None:
        if self._range_high is not None and self._range_low is not None:
            return self._range_high - self._range_low
        return None

    def mark_trade_taken(self) -> None:
        """Mark that a trade was filled — prevents re-entry unless reentry_allowed."""
        self._trade_taken = True

    def reset(self) -> None:
        """Reset per-trade state. _trade_taken and _orb_started survive to
        prevent the ORB from restarting after the first trade exits."""
        self._armed_bar_count = 0
        self._breakout_streak = 0
        self._breakout_direction = ""

    def re_range(self) -> None:
        """Reset range state for building a new range mid-session."""
        self._range_high = None
        self._range_low = None
        self._range_candle_count = 0
        self._range_volume_sum = 0.0
        self._armed_bar_count = 0
        self._orb_started = False  # allow _check_orb_start to trigger again
        self._breakout_streak = 0
        self._breakout_direction = ""
        logger.info("ORB re-range: building new range (#%d)", self._ranges_built + 1)

    def full_reset(self) -> None:
        """Full reset for a new session — clears everything including session flags."""
        self._range_high = None
        self._range_low = None
        self._range_candle_count = 0
        self._range_volume_sum = 0.0
        self._armed_bar_count = 0
        self._orb_started = False
        self._trade_taken = False
        self._breakout_streak = 0
        self._breakout_direction = ""
        self._ranges_built = 0

    def evaluate(self, state: FSMState, buf: CandleBuffer) -> Signal:
        """Produce a signal given current FSM state and candle buffer."""
        if state == FSMState.FLAT:
            return self._check_orb_start(buf)
        elif state == FSMState.ORB_BUILDING:
            return self._build_range(buf)
        elif state == FSMState.ORB_ARMED:
            return self._check_breakout(buf)
        else:
            # IN_TRADE / EXIT states are handled by Trader directly
            return Signal(action="none")

    def _check_orb_start(self, buf: CandleBuffer) -> Signal:
        """Trigger ORB_BUILDING on the first candle or after re-range."""
        if len(buf) == 0:
            return Signal(action="none", reason="No candles yet")

        # Once a trade has been taken, don't restart unless reentry is allowed
        if self._trade_taken and not self.config.reentry_allowed:
            return Signal(action="none", reason="ORB session complete — no re-entry")

        # Check max ranges cap
        if self._ranges_built >= self.config.max_ranges_per_session:
            return Signal(action="none", reason="Max ranges reached for session")

        if not self._orb_started:
            self._orb_started = True
            candle = buf.last
            self._range_high = candle.high
            self._range_low = candle.low
            self._range_candle_count = 1
            self._range_volume_sum = float(candle.volume)
            return Signal(action="orb_start", reason="Opening range building started")
        return Signal(action="none")

    def _build_range(self, buf: CandleBuffer) -> Signal:
        """Accumulate the opening range over N candles."""
        candle = buf.last
        if candle is None:
            return Signal(action="none")

        # Update range extremes
        if self._range_high is None or candle.high > self._range_high:
            self._range_high = candle.high
        if self._range_low is None or candle.low < self._range_low:
            self._range_low = candle.low

        self._range_candle_count += 1
        self._range_volume_sum += float(candle.volume)

        # Check if range window is complete
        if self._range_candle_count >= self.config.range_minutes:
            self._ranges_built += 1
            logger.info(
                "ORB range #%d set: high=%.2f, low=%.2f (%d candles)",
                self._ranges_built, self._range_high, self._range_low, self._range_candle_count,
            )
            self._armed_bar_count = 0
            return Signal(
                action="range_set",
                reason=f"Opening range #{self._ranges_built}: {self._range_low:.2f}-{self._range_high:.2f}",
            )

        return Signal(action="none", reason="Building opening range")

    def _check_breakout(self, buf: CandleBuffer) -> Signal:
        """Check for breakout above/below the opening range."""
        candle = buf.last
        if candle is None or self._range_high is None or self._range_low is None:
            return Signal(action="none")

        self._armed_bar_count += 1

        # Check expiry
        if self._armed_bar_count > self.config.max_wait_minutes:
            # Re-range if allowed and under the cap
            if (
                self.config.re_range_on_expiry
                and self._ranges_built < self.config.max_ranges_per_session
            ):
                logger.info(
                    "ORB range #%d expired — re-ranging (%d/%d max)",
                    self._ranges_built, self._ranges_built, self.config.max_ranges_per_session,
                )
                self.re_range()
                return Signal(action="range_expired_rerange", reason="ORB range expired — building new range")
            return Signal(action="range_expired", reason="ORB range expired — no breakout (max ranges reached)")

        range_height = self._range_high - self._range_low
        if range_height <= 0:
            return Signal(action="none", reason="Degenerate range")

        # Minimum range height filter — skip tiny ranges that produce fakeouts
        min_range_abs = self.config.min_range_pct / 100.0 * candle.close
        if range_height < min_range_abs:
            return Signal(action="none", reason=f"Range too narrow ({range_height:.2f} < {min_range_abs:.2f} = {self.config.min_range_pct}% of {candle.close:.2f})")

        # Min ATR filter — percentage-based, works across all price levels
        from icc.core.indicators import atr as calc_atr
        closes = buf.closes()
        highs = buf.highs()
        lows = buf.lows()
        if len(closes) >= 14:
            atr_vals = calc_atr(highs, lows, closes, 14)
            if atr_vals:
                min_atr_abs = self.config.min_atr_pct / 100.0 * candle.close
                if atr_vals[-1] < min_atr_abs:
                    return Signal(action="none", reason=f"ATR too low ({atr_vals[-1]:.2f} < {min_atr_abs:.2f} = {self.config.min_atr_pct}% of {candle.close:.2f})")

        # Volume confirmation (if enabled)
        if self.config.volume_confirmation and self._range_candle_count > 0:
            avg_vol = self._range_volume_sum / self._range_candle_count
            threshold = avg_vol * (self.config.volume_threshold_pct / 100.0)
            if candle.volume < threshold:
                # Volume too low — skip this candle
                if candle.close > self._range_high or candle.close < self._range_low:
                    return Signal(action="none", reason="Breakout rejected — low volume")

        # Calculate stop and target based on stop_mode
        if self.config.stop_mode == "midpoint":
            midpoint = (self._range_high + self._range_low) / 2.0
            long_stop = midpoint
            short_stop = midpoint
        else:  # "opposite"
            long_stop = self._range_low
            short_stop = self._range_high

        target_distance = range_height * self.config.target_multiplier
        needed = self.config.confirmation_bars

        # Track consecutive closes beyond range for confirmation
        if candle.close > self._range_high:
            if self._breakout_direction == "long":
                self._breakout_streak += 1
            else:
                self._breakout_direction = "long"
                self._breakout_streak = 1
        elif candle.close < self._range_low:
            if self._breakout_direction == "short":
                self._breakout_streak += 1
            else:
                self._breakout_direction = "short"
                self._breakout_streak = 1
        else:
            # Price back inside range — reset streak
            self._breakout_streak = 0
            self._breakout_direction = ""
            return Signal(action="none", reason="Waiting for breakout")

        # Log every breakout candle, but only enter after confirmation
        if self._breakout_direction == "long":
            logger.info(
                "ORB BREAKOUT LONG: close=%.2f > range_high=%.2f (%d/%d confirmed)",
                candle.close, self._range_high, self._breakout_streak, needed,
            )
            if self._breakout_streak < needed:
                return Signal(action="none", reason=f"Breakout confirming ({self._breakout_streak}/{needed})")
            entry = candle.close
            target = entry + target_distance
            return Signal(
                action="enter_long",
                entry_price=entry,
                stop_price=long_stop,
                target_price=target,
                reason=f"ORB breakout long: entry={entry:.2f}, stop={long_stop:.2f}, target={target:.2f}",
            )

        if self._breakout_direction == "short":
            logger.info(
                "ORB BREAKDOWN SHORT: close=%.2f < range_low=%.2f (%d/%d confirmed)",
                candle.close, self._range_low, self._breakout_streak, needed,
            )
            if self._breakout_streak < needed:
                return Signal(action="none", reason=f"Breakdown confirming ({self._breakout_streak}/{needed})")
            entry = candle.close
            target = entry - target_distance
            return Signal(
                action="enter_short",
                entry_price=entry,
                stop_price=short_stop,
                target_price=target,
                reason=f"ORB breakdown short: entry={entry:.2f}, stop={short_stop:.2f}, target={target:.2f}",
            )

        return Signal(action="none", reason="Waiting for breakout")
