"""Research agent — combines calendar + regime into confidence-based entry filter."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime
from typing import Optional

from icc.market.candle import CandleBuffer
from icc.research.calendar import CalendarState, EconomicCalendar
from icc.research.config import ResearchConfig
from icc.research.regime import RegimeDetector, RegimeState

logger = logging.getLogger(__name__)


@dataclass
class MarketContext:
    """Combined assessment from calendar + regime."""
    allowed: bool
    confidence: float
    reason: str
    calendar: CalendarState
    regime: RegimeState | None


class ResearchAgent:
    """Orchestrates calendar and regime checks for entry confidence filtering.

    Pure computation — no async, no threads. Runs on existing buffer data.
    """

    def __init__(self, config: ResearchConfig) -> None:
        self.config = config
        self._calendar = EconomicCalendar(config.calendar_file) if config.enabled else None
        self._regime = RegimeDetector(config) if config.enabled else None
        self._last_context: MarketContext | None = None

    def assess_entry(
        self,
        buffer: CandleBuffer,
        signal_direction: str,
        now: Optional[datetime] = None,
        win_rate_adj: float = 1.0,
    ) -> tuple[bool, str, float]:
        """Assess whether an entry should be allowed.

        Args:
            buffer: Recent candle data
            signal_direction: "long" or "short"
            now: Current time (defaults to datetime.now())

        Returns:
            (allowed, reason, confidence)
        """
        if not self.config.enabled:
            self._last_context = MarketContext(
                allowed=True,
                confidence=1.0,
                reason="Research agent disabled",
                calendar=CalendarState(in_blackout=False),
                regime=None,
            )
            return True, "Research agent disabled", 1.0

        if now is None:
            now = datetime.now()

        # 1. Calendar check (hard veto)
        cal_state = self._calendar.check(now) if self._calendar else CalendarState(
            in_blackout=False
        )
        if cal_state.in_blackout:
            reason = f"Economic calendar blackout: {cal_state.active_event}"
            self._last_context = MarketContext(
                allowed=False,
                confidence=0.0,
                reason=reason,
                calendar=cal_state,
                regime=None,
            )
            logger.info("Research VETO: %s", reason)
            return False, reason, 0.0

        # 2. Regime assessment (soft confidence)
        regime_state = self._regime.assess(buffer, signal_direction, now) if self._regime else None
        confidence = regime_state.confidence_mult if regime_state else 1.0

        # 2b. Apply win rate adjustment
        confidence *= win_rate_adj

        # 3. Apply minimum confidence threshold
        if confidence < self.config.min_confidence:
            reason = (
                f"Low confidence ({confidence:.3f} < {self.config.min_confidence}): "
                f"{regime_state.details if regime_state else {}}"
            )
            self._last_context = MarketContext(
                allowed=False,
                confidence=confidence,
                reason=reason,
                calendar=cal_state,
                regime=regime_state,
            )
            logger.info("Research VETO: %s", reason)
            return False, reason, confidence

        reason = f"Confidence {confidence:.3f} — OK"
        self._last_context = MarketContext(
            allowed=True,
            confidence=confidence,
            reason=reason,
            calendar=cal_state,
            regime=regime_state,
        )
        return True, reason, confidence

    def get_snapshot(self) -> dict:
        """Return current research state for dashboard/API."""
        if self._last_context is None:
            return {"status": "no_assessment", "enabled": self.config.enabled}

        ctx = self._last_context
        snapshot = {
            "enabled": self.config.enabled,
            "allowed": ctx.allowed,
            "confidence": ctx.confidence,
            "reason": ctx.reason,
            "calendar": {
                "in_blackout": ctx.calendar.in_blackout,
                "active_event": ctx.calendar.active_event,
                "blackout_end": (
                    ctx.calendar.blackout_end.isoformat()
                    if ctx.calendar.blackout_end
                    else None
                ),
            },
        }
        if ctx.regime is not None:
            snapshot["regime"] = {
                "atr_percentile": ctx.regime.atr_percentile,
                "atr_regime": ctx.regime.atr_regime,
                "session_phase": ctx.regime.session_phase,
                "vwap_aligned": ctx.regime.vwap_aligned,
                "confidence_mult": ctx.regime.confidence_mult,
                "details": ctx.regime.details,
            }
        return snapshot
