"""Order, Fill, Position dataclasses."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime

from icc.constants import OrderSide, OrderStatus, OrderType


@dataclass
class Order:
    order_type: OrderType
    side: OrderSide
    quantity: int = 1
    price: float | None = None
    status: OrderStatus = OrderStatus.PENDING
    order_id: str = ""
    broker_order_id: str = ""
    created_at: datetime = field(default_factory=datetime.utcnow)
    filled_price: float | None = None
    filled_at: datetime | None = None
    asset_info: dict | None = None  # Option contract details when instrument_type=OPTIONS


@dataclass
class Fill:
    order_id: str
    price: float
    quantity: int
    side: OrderSide
    timestamp: datetime = field(default_factory=datetime.utcnow)
    commission: float = 0.0


@dataclass
class Position:
    side: OrderSide
    entry_price: float
    quantity: int = 1
    stop_price: float = 0.0
    target_price: float = 0.0
    entry_time: datetime = field(default_factory=datetime.utcnow)
    bars_held: int = 0
    multiplier: float | None = None  # Override for options (e.g. 5.0 for MES options)
    entry_premium: float | None = None  # Premium paid at entry (options only)
    original_stop_price: float = 0.0
    breakeven_triggered: bool = False
    trailing_active: bool = False

    @property
    def is_long(self) -> bool:
        return self.side == OrderSide.BUY

    @property
    def is_option(self) -> bool:
        return self.entry_premium is not None

    def unrealized_pnl(self, current_price: float) -> float:
        """Compute unrealized P&L.

        For futures: (price_diff) * MES_POINT_VALUE * qty.
        For options: (current_premium - entry_premium) * multiplier * qty.
        ``current_price`` is the underlying price for futures, or the
        current option premium for options.
        """
        if self.is_option:
            mult = self.multiplier or 5.0
            return (current_price - self.entry_premium) * mult * self.quantity
        from icc.constants import MES_POINT_VALUE
        if self.is_long:
            return (current_price - self.entry_price) * MES_POINT_VALUE * self.quantity
        return (self.entry_price - current_price) * MES_POINT_VALUE * self.quantity
