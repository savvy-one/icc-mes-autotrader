"""BacktestBrokerAdapter — fill simulation."""

from __future__ import annotations

from datetime import datetime

from icc.broker.base import BrokerAdapter
from icc.constants import MES_TICK_SIZE, OrderSide, OrderType
from icc.oms.orders import Fill, Order


class BacktestBrokerAdapter(BrokerAdapter):
    """Simulates order fills for backtesting."""

    def __init__(self, slippage_ticks: int = 1, commission_per_side: float = 2.50):
        self.slippage_ticks = slippage_ticks
        self.commission_per_side = commission_per_side
        self._connected = False

    def connect(self) -> bool:
        self._connected = True
        return True

    def disconnect(self) -> None:
        self._connected = False

    def submit_order(self, order: Order) -> Fill | None:
        if order.price is None and order.order_type != OrderType.MARKET:
            return None

        # Simulate fill with slippage
        slippage = self.slippage_ticks * MES_TICK_SIZE
        if order.order_type == OrderType.MARKET:
            fill_price = order.price or 0.0
        elif order.side == OrderSide.BUY:
            fill_price = (order.price or 0.0) + slippage
        else:
            fill_price = (order.price or 0.0) - slippage

        return Fill(
            order_id=order.order_id,
            price=fill_price,
            quantity=order.quantity,
            side=order.side,
            timestamp=datetime.utcnow(),
            commission=self.commission_per_side,
        )

    def cancel_order(self, order: Order) -> bool:
        return True

    def get_positions(self) -> list[dict]:
        return []
