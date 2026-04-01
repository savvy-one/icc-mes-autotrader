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

            # Wait for IB fill — poll order status, then check positions
            import time
            fill_price = order.price or 0.0
            deadline = time.monotonic() + 10.0
            filled = False

            while time.monotonic() < deadline:
                if lumi_order.is_filled():
                    fp = lumi_order.get_fill_price()
                    if fp:
                        fill_price = fp
                    filled = True
                    logger.info("Order filled (order status) at %.4f", fill_price)
                    break
                time.sleep(0.3)

            if not filled:
                # Order status didn't update — check if position exists (IB filled
                # but Lumibot's order state machine lagged behind)
                try:
                    positions = self._strategy.get_positions()
                    for pos in positions:
                        if str(pos.asset) == str(asset) or (
                            hasattr(pos.asset, 'symbol') and pos.asset.symbol == asset.symbol
                        ):
                            filled = True
                            # Try to get fill price from the order one more time
                            fp = lumi_order.get_fill_price() if hasattr(lumi_order, "get_fill_price") else None
                            if fp:
                                fill_price = fp
                            logger.info(
                                "Order filled (position confirmed) at %.4f", fill_price,
                            )
                            break
                except Exception as e:
                    logger.debug("Position check after fill timeout: %s", e)

            if not filled:
                logger.warning(
                    "Order fill not confirmed after 10s — using price %.4f",
                    fill_price,
                )

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
