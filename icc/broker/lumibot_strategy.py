"""ICCLumibotStrategy — Lumibot strategy that runs ICC Trader inside on_trading_iteration()."""

from __future__ import annotations

import logging
from datetime import date, timedelta

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
            expiration=self._front_month_expiration(),
            multiplier=5,
        )

        event_bus = self.parameters.get("event_bus")

        # Wire up ICC components
        broker_adapter = LumibotBrokerAdapter(self)
        oms = OrderManager(broker_adapter)

        alert_router = AlertRouter()
        if event_bus is not None:
            alert_router.add_channel(WebSocketAlertChannel(event_bus))

        config = load_config("live")

        # Set up DB session for trade persistence
        from uuid import uuid4
        from icc.db.engine import get_session as get_db_session, init_db
        init_db(config.db_url)
        db_session = get_db_session(config.db_url)
        session_id = date.today().strftime("%Y%m%d") + "-" + uuid4().hex[:8]

        self.icc_trader = Trader(
            config=config,
            order_manager=oms,
            alert_router=alert_router,
            event_bus=event_bus,
            db_session=db_session,
            session_id=session_id,
        )
        logger.info("ICCLumibotStrategy initialized — asset=%s", self.asset)

    def on_trading_iteration(self):
        # Send heartbeat to keep watchdog alive even if bars are delayed
        event_bus = self.parameters.get("event_bus")
        if event_bus is not None:
            from icc.core.events import EventType
            event_bus.emit(EventType.CANDLE, {"heartbeat": True})

        bars = self.get_historical_prices(self.asset, 1, "minute", exchange="CME")
        if bars is None:
            print("[ICC] WARN: No bars object returned (None)", flush=True)
            return
        if bars.df.empty:
            print("[ICC] WARN: Bars dataframe is empty", flush=True)
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
        print(f"[ICC] Candle: {candle.timestamp} O={candle.open:.2f} H={candle.high:.2f} L={candle.low:.2f} C={candle.close:.2f} V={candle.volume}", flush=True)

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

    @staticmethod
    def _front_month_expiration() -> date:
        """Return the 3rd Friday of the current front-month quarterly contract.

        MES quarterly months: Mar(3), Jun(6), Sep(9), Dec(12).
        If today is past the 3rd Friday of the current quarter month,
        roll to the next quarter.
        """
        today = date.today()
        quarterly = [3, 6, 9, 12]

        for m in quarterly:
            y = today.year if m >= today.month else today.year + 1
            third_friday = _third_friday(y, m)
            if third_friday >= today:
                return third_friday

        # Wrap to March next year
        return _third_friday(today.year + 1, 3)


def _third_friday(year: int, month: int) -> date:
    """Return the 3rd Friday of the given month/year."""
    # First day of month
    first = date(year, month, 1)
    # Days until first Friday (Friday = 4)
    days_to_friday = (4 - first.weekday()) % 7
    first_friday = first + timedelta(days=days_to_friday)
    return first_friday + timedelta(weeks=2)
