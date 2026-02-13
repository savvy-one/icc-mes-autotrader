"""TradingSession — manages background trading thread lifecycle."""

from __future__ import annotations

import logging
import threading
from typing import Optional

from icc.alerts.base import AlertRouter
from icc.alerts.ws_alert import WebSocketAlertChannel
from icc.broker.backtest import BacktestBrokerAdapter
from icc.config import AppSettings, load_config
from icc.core.events import EventBus, EventType
from icc.core.trader import Trader
from icc.market.candle import Candle
from icc.market.feed import SimulatedLiveFeed
from icc.oms.manager import OrderManager

logger = logging.getLogger(__name__)


def _generate_sample_candles() -> list[Candle]:
    """Generate synthetic MES candles for demo/simulation."""
    import math
    from datetime import datetime, timedelta

    candles: list[Candle] = []
    base_price = 5200.0
    t = datetime(2024, 1, 15, 9, 30, 0)

    for i in range(120):
        # Simulate realistic price movement with trend + noise
        trend = math.sin(i * 0.05) * 15
        noise = math.sin(i * 0.3) * 5 + math.cos(i * 0.7) * 3
        mid = base_price + trend + noise

        o = mid + (math.sin(i * 0.2) * 2)
        h = mid + abs(math.sin(i * 0.4) * 4) + 1.5
        l = mid - abs(math.cos(i * 0.4) * 4) - 1.5
        c = mid + (math.cos(i * 0.15) * 3)
        vol = int(500 + abs(math.sin(i * 0.1)) * 800)

        candles.append(Candle(
            timestamp=t,
            open=round(o, 2),
            high=round(max(o, c, h), 2),
            low=round(min(o, c, l), 2),
            close=round(c, 2),
            volume=vol,
        ))
        t += timedelta(minutes=1)

    return candles


class TradingSession:
    """Manages a live trading session running in a background thread."""

    def __init__(self, event_bus: EventBus) -> None:
        self.event_bus = event_bus
        self._thread: Optional[threading.Thread] = None
        self._trader: Optional[Trader] = None
        self._feed: Optional[SimulatedLiveFeed] = None
        self._running = False
        self._config: Optional[AppSettings] = None
        self._mode: str = "simulated"
        self._lumi_trader = None
        self._lumi_strategy = None
        self._watchdog = None

    @property
    def is_running(self) -> bool:
        return self._running and self._thread is not None and self._thread.is_alive()

    def start(self, data_file: Optional[str] = None, delay: float = 1.0) -> None:
        """Start the trading session in a background thread."""
        if self.is_running:
            raise RuntimeError("Session already running")

        self._config = load_config("paper")

        # Load candles
        if data_file:
            from icc.backtest.data_loader import load_candles_csv
            candles = load_candles_csv(data_file)
        else:
            candles = _generate_sample_candles()

        self._feed = SimulatedLiveFeed(candles, delay=delay)

        # Set up broker + OMS
        broker = BacktestBrokerAdapter()
        oms = OrderManager(broker)

        # Set up alert router with WebSocket channel
        alert_router = AlertRouter()
        alert_router.add_channel(WebSocketAlertChannel(self.event_bus))

        self._trader = Trader(
            config=self._config,
            order_manager=oms,
            alert_router=alert_router,
            event_bus=self.event_bus,
        )

        self._running = True
        self._thread = threading.Thread(target=self._run_loop, daemon=True)
        self._thread.start()
        self.event_bus.emit(EventType.SESSION_STARTED)
        logger.info("Trading session started")

    def _run_loop(self) -> None:
        """Main trading loop (runs in background thread)."""
        try:
            for candle in self._feed:
                if not self._running:
                    break
                self._trader.on_candle(candle)
        except Exception as e:
            logger.exception("Trading loop error: %s", e)
        finally:
            self._running = False
            self.event_bus.emit(EventType.SESSION_STOPPED)
            logger.info("Trading session stopped")

    def start_live(self) -> None:
        """Start a LIVE trading session via Lumibot + Interactive Brokers."""
        if self.is_running:
            raise RuntimeError("Session already running")

        try:
            from lumibot.brokers import InteractiveBrokers
            from lumibot.traders import Trader as LumiTrader
        except ImportError:
            raise RuntimeError(
                "lumibot is not installed. Run: pip install 'icc-mes-autotrader[live]'"
            )

        from icc.broker.lumibot_strategy import ICCLumibotStrategy
        from icc.config import load_config

        self._config = load_config("live")
        ib_config = {
            "SOCKET_PORT": self._config.ib.socket_port,
            "CLIENT_ID": self._config.ib.client_id,
            "IP": self._config.ib.ip,
        }

        broker = InteractiveBrokers(ib_config)
        strategy = ICCLumibotStrategy(
            broker=broker,
            parameters={"event_bus": self.event_bus},
        )
        self._lumi_strategy = strategy

        self._lumi_trader = LumiTrader()
        self._lumi_trader.add_strategy(strategy)

        self._running = True
        self._mode = "live"
        self._thread = threading.Thread(
            target=self._run_live, args=(self._lumi_trader,), daemon=True
        )
        self._thread.start()
        self.event_bus.emit(EventType.SESSION_STARTED, {"mode": "live"})
        logger.info("LIVE trading session started (port %s)", self._config.ib.socket_port)

    def _run_live(self, lumi_trader) -> None:
        """Run Lumibot trader in background thread."""
        try:
            lumi_trader.run_all()
        except Exception as e:
            logger.exception("Lumibot live loop error: %s", e)
        finally:
            self._running = False
            self.event_bus.emit(EventType.SESSION_STOPPED, {"mode": "live"})
            logger.info("LIVE trading session stopped")

    def stop(self) -> None:
        """Gracefully stop the trading session."""
        self._running = False
        if self._feed:
            self._feed.stop()
        if self._lumi_trader is not None:
            try:
                self._lumi_trader.stop_all()
            except Exception as e:
                logger.error("Error stopping Lumibot trader: %s", e)
            self._lumi_trader = None
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=5.0)
        self._mode = "simulated"
        logger.info("Trading session stop requested")

    def flatten_and_stop(self) -> None:
        """End-of-session: flatten all positions, log summary, then stop."""
        logger.info("flatten_and_stop called — flattening positions")
        self.event_bus.emit(EventType.SESSION_FLATTEN, {"reason": "session_close"})

        self._flatten_positions()

        # Log session summary
        snapshot = self.get_snapshot()
        summary = {
            "final_pnl": snapshot.get("daily_pnl", 0.0) if snapshot.get("status") != "no_session" else 0.0,
            "trade_count": snapshot.get("trade_count", 0) if snapshot.get("status") != "no_session" else 0,
            "final_state": snapshot.get("fsm_state", "N/A") if snapshot.get("status") != "no_session" else "N/A",
        }
        logger.info("Session summary: PnL=%.2f, trades=%d, state=%s",
                     summary["final_pnl"], summary["trade_count"], summary["final_state"])
        self.event_bus.emit(EventType.SESSION_STOPPED, {"summary": summary})
        self.stop()

    def _flatten_positions(self) -> None:
        """Flatten positions at both ICC and broker level."""
        # ICC internal flatten
        if self._trader and not self._trader.positions.is_flat:
            last = self._trader.buffer.last
            if last:
                self._trader._exit_position(last.close, "session_flatten")
                logger.info("ICC internal position flattened")

        # Lumibot broker-level flatten
        if self._lumi_strategy is not None:
            try:
                self._lumi_strategy.flatten_positions()
                logger.info("Lumibot broker positions flattened")
            except Exception as e:
                logger.error("Error flattening Lumibot positions: %s", e)

    def kill(self) -> None:
        """Emergency kill — flatten positions and stop immediately."""
        logger.critical("EMERGENCY KILL activated")
        self.event_bus.emit(EventType.KILL_SWITCH, {"reason": "manual_kill"})

        self._flatten_positions()

        self._running = False
        if self._feed:
            self._feed.stop()
        if self._lumi_trader is not None:
            try:
                self._lumi_trader.stop_all()
            except Exception as e:
                logger.error("Error stopping Lumibot trader during kill: %s", e)
            self._lumi_trader = None
        self._lumi_strategy = None

    def notify_candle(self) -> None:
        """Notify the watchdog that a candle was received."""
        if self._watchdog is not None:
            self._watchdog.record_candle()

    def set_watchdog(self, watchdog) -> None:
        """Attach a Watchdog instance for health monitoring."""
        self._watchdog = watchdog

    def get_snapshot(self) -> dict:
        """Get current trader snapshot."""
        if self._trader is None:
            return {"status": "no_session"}
        snapshot = self._trader.get_snapshot()
        snapshot["session_running"] = self.is_running
        snapshot["mode"] = self._mode
        return snapshot
