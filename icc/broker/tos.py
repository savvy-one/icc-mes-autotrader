"""ThinkorswimAdapter — paperMoney (stub for MVP)."""

from __future__ import annotations

import logging

from icc.broker.base import BrokerAdapter
from icc.config import BrokerConfig
from icc.oms.orders import Fill, Order

logger = logging.getLogger(__name__)


class ThinkorswimAdapter(BrokerAdapter):
    """Stub adapter for thinkorswim paperMoney. Not implemented for MVP."""

    def __init__(self, config: BrokerConfig):
        self.config = config
        self._connected = False

    def connect(self) -> bool:
        logger.warning("ThinkorswimAdapter is a stub — not connected to real broker")
        self._connected = True
        return True

    def disconnect(self) -> None:
        self._connected = False

    def submit_order(self, order: Order) -> Fill | None:
        raise NotImplementedError(
            "ThinkorswimAdapter.submit_order not implemented. "
            "Use BacktestBrokerAdapter for testing."
        )

    def cancel_order(self, order: Order) -> bool:
        raise NotImplementedError("ThinkorswimAdapter.cancel_order not implemented")

    def get_positions(self) -> list[dict]:
        raise NotImplementedError("ThinkorswimAdapter.get_positions not implemented")
