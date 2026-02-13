"""ICCLumibotStrategy — Lumibot strategy that runs ICC Trader inside on_trading_iteration()."""

from __future__ import annotations

import logging

from lumibot.entities import Asset
from lumibot.strategies import Strategy

from icc.alerts.base import AlertRouter
from icc.alerts.ws_alert import WebSocketAlertChannel
from icc.broker.lumibot_adapter import LumibotBrokerAdapter
from icc.config import load_config
from icc.core.trader import Trader
from icc.market.candle import Candle
from icc.oms.manager import OrderManager

logger = logging.getLogger(__name__)


class ICCLumibotStrategy(Strategy):
    """Bridges Lumibot's lifecycle into ICC's Trader.on_candle().

    Lumibot drives the iteration loop (sleeptime = "1M" for 1-min bars).
    Each iteration fetches the latest bar from IB, converts it to an ICC
    Candle, and feeds it into the ICC engine.
    """

    parameters = {
        "event_bus": None,
    }

    def initialize(self):
        self.sleeptime = "1M"  # 1-minute iteration
        self.asset = Asset(
            symbol="MES",
            asset_type=Asset.AssetType.FUTURE,
            expiration=Asset.get_expiration_date_for_contract_month(
                symbol="MES", exchange="CME"
            ) if hasattr(Asset, "get_expiration_date_for_contract_month") else None,
        )

        event_bus = self.parameters.get("event_bus")

        # Wire up ICC components
        broker_adapter = LumibotBrokerAdapter(self)
        oms = OrderManager(broker_adapter)

        alert_router = AlertRouter()
        if event_bus is not None:
            alert_router.add_channel(WebSocketAlertChannel(event_bus))

        config = load_config("live")
        self.icc_trader = Trader(
            config=config,
            order_manager=oms,
            alert_router=alert_router,
            event_bus=event_bus,
        )
        logger.info("ICCLumibotStrategy initialized — asset=%s", self.asset)

    def on_trading_iteration(self):
        bars = self.get_historical_prices(self.asset, 1, "minute")
        if bars is None or bars.df.empty:
            logger.debug("No bars returned, skipping iteration")
            return

        row = bars.df.iloc[-1]
        candle = Candle(
            timestamp=row.name.to_pydatetime(),
            open=float(row["open"]),
            high=float(row["high"]),
            low=float(row["low"]),
            close=float(row["close"]),
            volume=int(row.get("volume", 0)),
        )

        self.icc_trader.on_candle(candle)

    def on_abrupt_closing(self):
        logger.warning("Lumibot abrupt closing — flattening positions")
        if not self.icc_trader.positions.is_flat:
            last = self.icc_trader.buffer.last
            if last:
                self.icc_trader._exit_position(last.close, "emergency_exit")

    def flatten_positions(self):
        """Flatten all positions at broker level via Lumibot sell_all."""
        logger.info("Flattening all positions via Lumibot sell_all()")
        try:
            self.sell_all()
        except Exception as e:
            logger.error("Error in sell_all: %s", e)
        # Also flatten ICC internal position
        if not self.icc_trader.positions.is_flat:
            last = self.icc_trader.buffer.last
            if last:
                self.icc_trader._exit_position(last.close, "session_flatten")

    def on_bot_crash(self, error):
        logger.critical("Lumibot bot crash: %s", error)
        self.on_abrupt_closing()
