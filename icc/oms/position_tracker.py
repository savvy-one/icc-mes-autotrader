"""PositionTracker — real-time P&L."""

from __future__ import annotations

import logging

from icc.constants import MES_POINT_VALUE, OrderSide
from icc.oms.orders import Position

logger = logging.getLogger(__name__)


class PositionTracker:
    def __init__(self) -> None:
        self.position: Position | None = None
        self.closed_pnl: float = 0.0

    @property
    def is_flat(self) -> bool:
        return self.position is None

    @property
    def open_position_count(self) -> int:
        return 0 if self.position is None else 1

    def open_position(self, side: OrderSide, entry_price: float,
                      stop_price: float, target_price: float,
                      quantity: int = 1) -> Position:
        if self.position is not None:
            raise RuntimeError("Already holding a position")
        self.position = Position(
            side=side,
            entry_price=entry_price,
            quantity=quantity,
            stop_price=stop_price,
            target_price=target_price,
        )
        logger.info("Opened %s position at %.2f", side.value, entry_price)
        return self.position

    def close_position(self, exit_price: float, commission: float = 0.0) -> float:
        if self.position is None:
            raise RuntimeError("No position to close")
        pnl = self.position.unrealized_pnl(exit_price) - commission
        logger.info(
            "Closed position at %.2f, PnL=%.2f (commission=%.2f)",
            exit_price, pnl, commission,
        )
        self.closed_pnl += pnl
        self.position = None
        return pnl

    def check_stop_target(self, candle_high: float, candle_low: float) -> str | None:
        """Check if stop or target hit. Returns 'stop_hit', 'target_hit', or None."""
        if self.position is None:
            return None

        pos = self.position
        if pos.is_long:
            if candle_low <= pos.stop_price:
                return "stop_hit"
            if candle_high >= pos.target_price:
                return "target_hit"
        else:
            if candle_high >= pos.stop_price:
                return "stop_hit"
            if candle_low <= pos.target_price:
                return "target_hit"
        return None

    def increment_bars(self) -> int:
        if self.position is not None:
            self.position.bars_held += 1
            return self.position.bars_held
        return 0

    def unrealized_pnl(self, current_price: float) -> float:
        if self.position is None:
            return 0.0
        return self.position.unrealized_pnl(current_price)
