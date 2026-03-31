"""Volatility and session regime detector."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime, time
from typing import Optional

from icc.market.candle import CandleBuffer
from icc.research.config import ResearchConfig

logger = logging.getLogger(__name__)

# Session boundaries (ET)
SESSION_OPEN = time(9, 30)
SESSION_CLOSE = time(16, 0)


@dataclass
class RegimeState:
    """Result of regime assessment."""
    atr_percentile: float  # 0.0 - 1.0
    atr_regime: str        # "low", "normal", "high", "extreme"
    session_phase: str     # "opening", "mid", "closing", "outside"
    vwap_aligned: bool     # True if signal direction aligns with VWAP
    confidence_mult: float # Combined multiplier (all factors)
    details: dict


class RegimeDetector:
    """Assesses market regime from candle buffer data."""

    def __init__(self, config: ResearchConfig) -> None:
        self.config = config

    def assess(self, buffer: CandleBuffer, signal_direction: str,
               now: Optional[datetime] = None) -> RegimeState:
        """Assess regime for given buffer and signal direction.

        Args:
            buffer: Recent candle data
            signal_direction: "long" or "short"
            now: Current time (defaults to datetime.now())

        Returns:
            RegimeState with combined confidence multiplier
        """
        if now is None:
            now = datetime.now()

        mult = 1.0
        details: dict = {}

        # 1. ATR percentile
        atr_pct, atr_regime, atr_mult = self._assess_atr(buffer)
        mult *= atr_mult
        details["atr_percentile"] = round(atr_pct, 3)
        details["atr_regime"] = atr_regime
        details["atr_mult"] = atr_mult

        # 2. Session phase
        phase, phase_mult = self._assess_session_phase(now)
        mult *= phase_mult
        details["session_phase"] = phase
        details["phase_mult"] = phase_mult

        # 3. VWAP alignment
        vwap_aligned, vwap_mult = self._assess_vwap(buffer, signal_direction)
        mult *= vwap_mult
        details["vwap_aligned"] = vwap_aligned
        details["vwap_mult"] = vwap_mult

        return RegimeState(
            atr_percentile=atr_pct,
            atr_regime=atr_regime,
            session_phase=phase,
            vwap_aligned=vwap_aligned,
            confidence_mult=round(mult, 4),
            details=details,
        )

    def _assess_atr(self, buffer: CandleBuffer) -> tuple[float, str, float]:
        """Compute ATR percentile and regime.

        Returns (percentile, regime_name, multiplier).
        """
        candles = list(buffer)
        if len(candles) < 15:
            return 0.5, "normal", 1.0

        # Compute ATR values (true range) for available candles
        trs = []
        for i in range(1, len(candles)):
            high = candles[i].high
            low = candles[i].low
            prev_close = candles[i - 1].close
            tr = max(high - low, abs(high - prev_close), abs(low - prev_close))
            trs.append(tr)

        if not trs:
            return 0.5, "normal", 1.0

        # Current ATR (14-period average of most recent TRs)
        period = min(14, len(trs))
        current_atr = sum(trs[-period:]) / period

        # Rank against lookback window
        lookback = min(self.config.atr_lookback, len(trs))
        lookback_trs = trs[-lookback:]
        sorted_trs = sorted(lookback_trs)
        # Percentile rank of current ATR
        rank = sum(1 for x in sorted_trs if x <= current_atr)
        percentile = rank / len(sorted_trs)

        if percentile >= self.config.atr_extreme_pct:
            return percentile, "extreme", self.config.extreme_vol_mult
        elif percentile >= 0.75:
            return percentile, "high", self.config.high_vol_mult
        elif percentile <= self.config.atr_low_pct:
            return percentile, "low", self.config.low_vol_mult
        else:
            return percentile, "normal", 1.0

    def _assess_session_phase(self, now: datetime) -> tuple[str, float]:
        """Determine session phase and multiplier."""
        current_time = now.time()

        # Outside market hours
        if current_time < SESSION_OPEN or current_time >= SESSION_CLOSE:
            return "outside", 1.0

        # Opening phase
        from datetime import timedelta
        opening_end = (
            datetime.combine(now.date(), SESSION_OPEN)
            + timedelta(minutes=self.config.opening_minutes)
        ).time()
        if current_time < opening_end:
            return "opening", self.config.opening_mult

        # Closing phase
        closing_start = (
            datetime.combine(now.date(), SESSION_CLOSE)
            - timedelta(minutes=self.config.closing_minutes)
        ).time()
        if current_time >= closing_start:
            return "closing", self.config.closing_mult

        return "mid", 1.0

    def _assess_vwap(self, buffer: CandleBuffer,
                     signal_direction: str) -> tuple[bool, float]:
        """Check if signal direction aligns with VWAP.

        Simple VWAP: volume-weighted average price from buffer.
        If price is above VWAP and signal is long → aligned.
        If price is below VWAP and signal is short → aligned.
        """
        candles = list(buffer)
        if len(candles) < 10:
            return True, 1.0

        # Compute VWAP
        total_pv = 0.0
        total_vol = 0
        for c in candles:
            typical = (c.high + c.low + c.close) / 3
            total_pv += typical * c.volume
            total_vol += c.volume

        if total_vol == 0:
            return True, 1.0

        vwap = total_pv / total_vol
        last_close = candles[-1].close

        if signal_direction == "long":
            aligned = last_close >= vwap
        elif signal_direction == "short":
            aligned = last_close <= vwap
        else:
            aligned = True

        if aligned:
            return True, 1.0
        return False, self.config.counter_vwap_mult
