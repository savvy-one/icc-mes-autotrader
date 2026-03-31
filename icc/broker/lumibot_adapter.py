"""LumibotBrokerAdapter — wraps Lumibot's order API into ICC's BrokerAdapter ABC."""

from __future__ import annotations

import logging
from datetime import datetime
from typing import TYPE_CHECKING

from icc.broker.base import BrokerAdapter
from icc.constants import OrderSide
from icc.oms.orders import Fill, Order

if TYPE_CHECKING:
    from lumibot.strategies import Strategy as LumibotStrategy

logger = logging.getLogger(__name__)


class LumibotBrokerAdapter(BrokerAdapter):
    """Delegates order operations to a Lumibot strategy instance.

    The parent Lumibot strategy owns the broker connection; this adapter
    translates ICC Order objects into Lumibot create_order / submit_order calls.
    """

    def __init__(self, strategy: LumibotStrategy) -> None:
        self._strategy = strategy

    def submit_order(self, order: Order) -> Fill | None:
        try:
            from lumibot.entities import Asset

            # Use option asset if order carries option contract info
            if order.asset_info and order.asset_info.get("asset_type") == "OPTION":
                from datetime import date as _date

                exp = order.asset_info["expiration"]
                expiration = (
                    _date.fromisoformat(exp) if isinstance(exp, str) else exp
                )
                asset = Asset(
                    symbol=order.asset_info["underlying"],
                    asset_type=Asset.AssetType.OPTION,
                    expiration=expiration,
                    strike=order.asset_info["strike"],
                    right=order.asset_info["option_type"].lower(),
                    multiplier=int(order.asset_info.get("multiplier", 5)),
                )
            else:
                asset = self._strategy.asset  # futures asset

            side = "buy" if order.side == OrderSide.BUY else "sell"

            lumi_order = self._strategy.create_order(
                asset=asset,
                quantity=order.quantity,
                side=side,
                type="market",  # execute at market for simplicity
            )
            self._strategy.submit_order(lumi_order)

            # Wait for IB fill (async — poll up to 10 seconds)
            import time
            fill_price = order.price or 0.0
            deadline = time.monotonic() + 10.0
            while time.monotonic() < deadline:
                if lumi_order.is_filled():
                    fp = lumi_order.get_fill_price()
                    if fp:
                        fill_price = fp
                        logger.info("Order filled at %.4f", fill_price)
                    break
                time.sleep(0.2)
            else:
                # Timeout — use best available price
                logger.warning(
                    "Order fill timeout after 10s — using submitted price %.4f",
                    fill_price,
                )
                if hasattr(lumi_order, "get_fill_price"):
                    fp = lumi_order.get_fill_price()
                    if fp:
                        fill_price = fp

            return Fill(
                order_id=order.order_id,
                price=fill_price,
                quantity=order.quantity,
                side=order.side,
                timestamp=datetime.utcnow(),
            )
        except Exception as e:
            logger.error("Lumibot order submission failed: %s", e)
            return None

    def cancel_order(self, order: Order) -> bool:
        try:
            self._strategy.cancel_order(order.broker_order_id)
            return True
        except Exception as e:
            logger.error("Lumibot cancel failed: %s", e)
            return False

    def get_positions(self) -> list[dict]:
        try:
            positions = self._strategy.get_positions()
            return [
                {
                    "symbol": str(p.asset),
                    "quantity": p.quantity,
                }
                for p in positions
            ]
        except Exception as e:
            logger.error("Lumibot get_positions failed: %s", e)
            return []

    def connect(self) -> bool:
        # Lumibot manages its own connection lifecycle
        return True

    def disconnect(self) -> None:
        # Lumibot manages its own connection lifecycle
        pass
