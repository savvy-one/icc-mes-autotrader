"""OrderManager — submit, cancel, retry (3x, 2s backoff)."""

from __future__ import annotations

import logging
import time
import uuid
from typing import TYPE_CHECKING

from icc.constants import OrderStatus
from icc.oms.orders import Fill, Order

if TYPE_CHECKING:
    from icc.broker.base import BrokerAdapter

logger = logging.getLogger(__name__)

MAX_RETRIES = 3
RETRY_BACKOFF_SEC = 2.0


class OrderManager:
    def __init__(self, broker: BrokerAdapter):
        self.broker = broker
        self.orders: dict[str, Order] = {}

    def submit(self, order: Order) -> Order:
        order.order_id = str(uuid.uuid4())[:8]
        order.status = OrderStatus.SUBMITTED
        self.orders[order.order_id] = order

        for attempt in range(1, MAX_RETRIES + 1):
            try:
                fill = self.broker.submit_order(order)
                if fill is not None:
                    order.status = OrderStatus.FILLED
                    order.filled_price = fill.price
                    order.filled_at = fill.timestamp
                    logger.info("Order %s filled at %.2f", order.order_id, fill.price)
                    return order
                else:
                    order.status = OrderStatus.REJECTED
                    logger.warning("Order %s rejected (attempt %d)", order.order_id, attempt)
            except Exception as e:
                logger.error("Order %s error (attempt %d): %s", order.order_id, attempt, e)

            if attempt < MAX_RETRIES:
                time.sleep(RETRY_BACKOFF_SEC * attempt)

        order.status = OrderStatus.REJECTED
        logger.error("Order %s failed after %d retries", order.order_id, MAX_RETRIES)
        return order

    def cancel(self, order_id: str) -> bool:
        order = self.orders.get(order_id)
        if order is None or order.status in (OrderStatus.FILLED, OrderStatus.CANCELLED):
            return False
        try:
            self.broker.cancel_order(order)
            order.status = OrderStatus.CANCELLED
            return True
        except Exception as e:
            logger.error("Cancel failed for %s: %s", order_id, e)
            return False

    def get_order(self, order_id: str) -> Order | None:
        return self.orders.get(order_id)
