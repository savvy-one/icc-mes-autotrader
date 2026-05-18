"""ICCLumibotStrategy — Lumibot strategy that runs ICC Trader inside on_trading_iteration().

Supports multi-ticker mode: creates one Trader per ticker, monitors all ORB
ranges simultaneously, and takes the first clean breakout.
"""

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
    Each iteration fetches the latest bar per ticker from yfinance, converts
    to ICC Candle, and feeds into the appropriate Trader.

    Multi-ticker: all tickers build ORB ranges simultaneously; the first
    clean breakout wins (only one position at a time across all tickers).
    """

    parameters = {
        "event_bus": None,
        "instrument_type": "FUTURES",
        "option_underlying": "MES",
        "strategy_name": "ICC",
        "tickers": None,  # e.g. ["SPY", "QQQ", "NVDA", "AAPL"]
    }

    def initialize(self):
        self.sleeptime = "1M"  # 1-minute iteration
        # MES futures asset (for IB candle attempts in single-ticker/futures mode)
        front_exp = self._front_month_expiration()
        self.asset = Asset(
            symbol="MES",
            asset_type=Asset.AssetType.FUTURE,
            expiration=front_exp,
            multiplier=5,
        )
        print(f"[ICC] MES contract expiration: {front_exp}", flush=True)

        print(f"[ICC] initialize() self.parameters = {self.parameters}", flush=True)
        event_bus = self.parameters.get("event_bus")
        instrument_type = self.parameters.get("instrument_type", "FUTURES")
        option_underlying = self.parameters.get("option_underlying", "MES")
        strategy_name = self.parameters.get("strategy_name", "ICC")

        config = load_config("live")
        config.options.instrument_type = instrument_type
        config.options.underlying = option_underlying
        config.strategy_name = strategy_name

        # Determine tickers for multi-ticker mode
        tickers_param = self.parameters.get("tickers")
        if tickers_param:
            self._tickers = list(tickers_param)
        elif instrument_type == "OPTIONS" and strategy_name == "ORB":
            self._tickers = list(config.options.tickers)
        else:
            self._tickers = [option_underlying]

        self._multi_ticker = len(self._tickers) > 1
        print(f"[ICC] {'Multi' if self._multi_ticker else 'Single'}-ticker mode: {self._tickers}", flush=True)

        # Shared components
        broker_adapter = LumibotBrokerAdapter(self)
        alert_router = AlertRouter()
        if event_bus is not None:
            alert_router.add_channel(WebSocketAlertChannel(event_bus))

        from uuid import uuid4
        from icc.db.engine import get_session as get_db_session, init_db
        init_db(config.db_url)
        db_session = get_db_session(config.db_url)
        session_id = date.today().strftime("%Y%m%d") + "-" + uuid4().hex[:8]

        # Settlement tracker (shared across tickers — one $500 account)
        settlement_tracker = None
        if config.settlement.enabled:
            from icc.core.settlement import SettlementTracker
            from icc.broker.cash_provider import LumibotCashProvider
            cash_provider = LumibotCashProvider(self)
            settlement_tracker = SettlementTracker(
                total_capital=config.risk.account_size,
                safety_buffer=config.settlement.safety_buffer,
                tranches=config.settlement.tranches,
                max_trades_per_tranche=config.settlement.max_trades_per_tranche,
                cash_provider=cash_provider,
            )

        # Research agent (shared)
        research_agent = None
        if config.research.enabled:
            from icc.research.agent import ResearchAgent
            from icc.research.config import ResearchConfig as RAConfig
            ra_config = RAConfig(**config.research.model_dump())
            research_agent = ResearchAgent(ra_config)

        # Shared risk engine across all tickers (one account, shared cooldowns).
        # db_session enables RiskState persistence across process restarts so the
        # kill switch / daily PnL survive a launchd respawn mid-session.
        from icc.core.risk import RiskEngine
        shared_risk = RiskEngine(
            config.risk,
            settlement_tracker=settlement_tracker,
            db_session=db_session,
        )

        # Create one Trader per ticker
        self._traders: dict[str, Trader] = {}
        self._active_ticker: str | None = None

        for ticker in self._tickers:
            ticker_oms = OrderManager(broker_adapter)

            # Per-ticker config with its own underlying
            ticker_config = load_config("live")
            ticker_config.options.instrument_type = instrument_type
            ticker_config.options.underlying = ticker
            ticker_config.strategy_name = strategy_name

            # Option chain resolver per ticker
            option_chain_resolver = None
            if instrument_type == "OPTIONS":
                from icc.broker.option_chain import (
                    LumibotOptionChainProvider,
                    OptionChainResolver,
                )
                option_provider = LumibotOptionChainProvider(self)
                ticker_max_premium = config.options.per_ticker_max_premium.get(
                    ticker, config.options.max_premium
                )
                option_chain_resolver = OptionChainResolver(
                    provider=option_provider,
                    underlying=ticker,
                    strike_mode=config.options.strike_mode,
                    expiration_mode=config.options.expiration_mode,
                    expiration_guard_minutes=config.options.expiration_guard_minutes,
                    max_premium=ticker_max_premium,
                    min_premium=config.options.min_premium,
                    otm_fallback=config.options.otm_fallback,
                )

            trader = Trader(
                config=ticker_config,
                order_manager=ticker_oms,
                alert_router=alert_router,
                event_bus=event_bus,
                db_session=db_session,
                session_id=f"{session_id}-{ticker}",
                settlement_tracker=settlement_tracker,
                research_agent=research_agent,
                option_chain_resolver=option_chain_resolver,
                shared_risk_engine=shared_risk,
            )

            # Wire live premium feed for options
            if instrument_type == "OPTIONS":
                trader._premium_feed = self._get_live_option_premium

            self._traders[ticker] = trader
            print(f"[ICC] Trader created for {ticker}", flush=True)

        # Backward compat: icc_trader points to first ticker's trader (updated dynamically)
        self.icc_trader = self._traders[self._tickers[0]]

        self._option_chain_tested = instrument_type != "OPTIONS"
        self._nextorderid_patched = False
        print(f"[ICC] ICCLumibotStrategy initialized — {len(self._tickers)} ticker(s)", flush=True)

    # ---- Candle fetching ----

    def _get_candle_for(self, ticker: str) -> Candle | None:
        """Get latest 1-min candle for a specific ticker via yfinance."""
        try:
            from icc.broker.option_chain import _yf_get_ticker
            yf_ticker = _yf_get_ticker(ticker)
            df = yf_ticker.history(period="1d", interval="1m")
            if df.empty:
                return None
            row = df.iloc[-1]
            return Candle(
                timestamp=row.name.to_pydatetime(),
                open=float(row["Open"]),
                high=float(row["High"]),
                low=float(row["Low"]),
                close=float(row["Close"]),
                volume=int(row.get("Volume", 0)),
            )
        except Exception as e:
            logger.debug("yfinance candle for %s failed: %s", ticker, e)
            return None

    def _get_candle(self):
        """Get latest 1-min candle. Tries IB MES first, falls back to yfinance SPY."""
        # Try IB MES futures
        bars = self.get_historical_prices(self.asset, 1, "minute", exchange="CME")
        if bars is not None and not bars.df.empty:
            row = bars.df.iloc[-1]
            vol = int(row.get("volume", 0))
            if vol > 0 or row["open"] != row["close"]:
                return Candle(
                    timestamp=row.name.to_pydatetime(),
                    open=float(row["open"]),
                    high=float(row["high"]),
                    low=float(row["low"]),
                    close=float(row["close"]),
                    volume=vol,
                )

        # Fallback: yfinance SPY 1-min bars
        if not getattr(self, '_yf_fallback_logged', False):
            print("[ICC] MES data unavailable, falling back to yfinance SPY candles", flush=True)
            self._yf_fallback_logged = True
        return self._get_candle_for("SPY")

    # ---- Option chain diagnostics ----

    def _enable_delayed_data(self) -> None:
        """Request delayed market data for instruments without real-time subscription."""
        try:
            if hasattr(self.broker, 'ib') and self.broker.ib is not None:
                self.broker.ib.reqMarketDataType(3)
                print("[ICC] Enabled delayed market data (type 3) for unsubscribed instruments", flush=True)
        except Exception as e:
            print(f"[ICC] Failed to enable delayed data: {e}", flush=True)

    def _test_option_chain(self) -> None:
        """One-time diagnostic: test option chain access for the first ticker."""
        self._option_chain_tested = True
        self._enable_delayed_data()
        # Test with the first ticker
        first_ticker = self._tickers[0]
        trader = self._traders[first_ticker]
        resolver = trader._option_resolver
        if resolver is None:
            return
        try:
            exps = resolver._provider.get_option_expirations(first_ticker)
            print(f"[ICC] Option chain test: {len(exps)} expirations for {first_ticker}", flush=True)
            if exps:
                print(f"[ICC]   Nearest: {exps[:5]}", flush=True)
                price = resolver._provider.get_underlying_price(first_ticker)
                print(f"[ICC]   {first_ticker} price: {price}", flush=True)
            else:
                print("[ICC]   WARNING: No expirations — option trading will fail!", flush=True)
        except Exception as e:
            print(f"[ICC]   Option chain test error: {e}", flush=True)

    # ---- Order ID timeout patch ----

    def _patch_next_order_id(self) -> None:
        """Monkey-patch IBApp.nextOrderId with a 30-second timeout.

        The original Lumibot implementation loops forever waiting for
        nextValidOrderId, which hangs if IB Gateway disconnects or
        multiple clients compete for the connection.
        """
        self._nextorderid_patched = True

        if not hasattr(self, 'broker') or self.broker is None:
            print("[ICC] broker not yet available — skipping nextOrderId patch", flush=True)
            return
        if not hasattr(self.broker, 'ib') or self.broker.ib is None:
            print("[ICC] broker.ib not yet available — skipping nextOrderId patch", flush=True)
            return

        ib_app = self.broker.ib

        _wait_logged_at = [0.0]  # mutable to allow closure update

        def nextOrderId_with_timeout():
            import time
            timeout = 30.0
            start = time.monotonic()
            while not hasattr(ib_app, "nextValidOrderId"):
                elapsed = time.monotonic() - start
                if elapsed >= timeout:
                    logger.error(
                        "nextOrderId timed out after %.0fs — IB Gateway not responding",
                        timeout,
                    )
                    raise TimeoutError(
                        f"nextOrderId wait exceeded {timeout}s — "
                        "IB Gateway not responding with nextValidOrderId"
                    )
                # Log once every 5 seconds instead of every 0.1s
                now = time.monotonic()
                if now - _wait_logged_at[0] >= 5.0:
                    logger.warning("Waiting for nextValidOrderId (%.0fs elapsed)", elapsed)
                    _wait_logged_at[0] = now
                time.sleep(0.1)
            oid = ib_app.nextValidOrderId
            ib_app.nextValidOrderId += 1
            return oid

        ib_app.nextOrderId = nextOrderId_with_timeout
        # Also patch the class to catch any other IBApp instances
        type(ib_app).nextOrderId = lambda self_: nextOrderId_with_timeout()
        print("[ICC] Patched IBApp.nextOrderId with 30s timeout", flush=True)

    # ---- Main trading loop ----

    def on_trading_iteration(self):
        # One-time monkey-patch for nextOrderId timeout
        if not self._nextorderid_patched:
            self._patch_next_order_id()

        # One-time option chain diagnostic
        if not self._option_chain_tested:
            self._test_option_chain()

        # Heartbeat
        event_bus = self.parameters.get("event_bus")
        if event_bus is not None:
            from icc.core.events import EventType
            event_bus.emit(EventType.CANDLE, {"heartbeat": True})

        if self._multi_ticker:
            self._multi_ticker_iteration()
        else:
            self._single_ticker_iteration()

    def _single_ticker_iteration(self):
        """Original single-ticker flow."""
        ticker = self._tickers[0]
        # For futures/MES, try IB first; for equities, go straight to yfinance
        if self.parameters.get("instrument_type") == "FUTURES":
            candle = self._get_candle()
        else:
            candle = self._get_candle_for(ticker)
        if candle is None:
            return
        print(f"[ICC] [{ticker}] Candle: {candle.timestamp} O={candle.open:.2f} H={candle.high:.2f} L={candle.low:.2f} C={candle.close:.2f} V={candle.volume}", flush=True)
        self.icc_trader.on_candle(candle)

    def _multi_ticker_iteration(self):
        """Multi-ticker flow: feed all tickers, first breakout wins."""
        for ticker in self._tickers:
            candle = self._get_candle_for(ticker)
            if candle is None:
                continue

            trader = self._traders[ticker]

            if self._active_ticker is None:
                # No position across any ticker — all can evaluate
                trader.on_candle(candle)
                if not trader.positions.is_flat:
                    self._active_ticker = ticker
                    self.icc_trader = trader  # point snapshot to active
                    print(f"[ICC] MULTI: {ticker} entered position — other tickers locked", flush=True)
                    break  # skip remaining tickers this iteration
            elif self._active_ticker == ticker:
                # This ticker has the active position — manage it
                trader.on_candle(candle)
                if trader.positions.is_flat:
                    self._active_ticker = None
                    self.icc_trader = self._traders[self._tickers[0]]
                    print(f"[ICC] MULTI: {ticker} position closed — all tickers unlocked", flush=True)
            else:
                # Another ticker holds the position — just buffer candles
                # so ORB range building continues
                trader.buffer.append(candle)

        # Log ORB state across tickers periodically
        if not getattr(self, '_orb_state_logged_bar', 0) % 5:
            self._log_orb_state()
        self._orb_state_logged_bar = getattr(self, '_orb_state_logged_bar', 0) + 1

    def _log_orb_state(self):
        """Log ORB range state for all tickers."""
        from icc.core.orb_strategy import ORBStrategyEngine
        parts = []
        for ticker in self._tickers:
            trader = self._traders[ticker]
            strat = trader.strategy
            if isinstance(strat, ORBStrategyEngine):
                rh = strat._range_high
                rl = strat._range_low
                state = trader.fsm.state.value
                if rh is not None and rl is not None:
                    parts.append(f"{ticker}[{state}]={rl:.2f}-{rh:.2f}")
                else:
                    parts.append(f"{ticker}[{state}]")
        if parts:
            active = f" active={self._active_ticker}" if self._active_ticker else ""
            print(f"[ICC] ORB ranges: {' | '.join(parts)}{active}", flush=True)

    # ---- Lifecycle ----

    def on_abrupt_closing(self):
        logger.warning("Lumibot abrupt closing — flattening positions")
        for ticker, trader in self._traders.items():
            if not trader.positions.is_flat:
                last = trader.buffer.last
                if last:
                    trader._exit_position(last.close, "emergency_exit")

    def flatten_positions(self):
        """Flatten all positions at broker level via Lumibot sell_all."""
        logger.info("Flattening all positions via Lumibot sell_all()")
        try:
            self.sell_all()
        except Exception as e:
            logger.error("Error in sell_all: %s", e)
        # Flatten ICC internal positions across all tickers
        for ticker, trader in self._traders.items():
            if not trader.positions.is_flat:
                last = trader.buffer.last
                if last:
                    trader._exit_position(last.close, "session_flatten")

    def on_bot_crash(self, error):
        logger.critical("Lumibot bot crash: %s", error)
        self.on_abrupt_closing()

    def _get_live_option_premium(self, contract) -> float | None:
        """Fetch option premium — yfinance first, IB fallback.

        yfinance is tried first to avoid IB market data subscription errors
        (e.g. NASDAQ TotalView) that spam logs every iteration.
        """
        # Primary: yfinance (no subscription required)
        from icc.broker.option_chain import _yf_get_option_premium
        yf_price = _yf_get_option_premium(
            contract.underlying, contract.expiration,
            contract.strike, contract.option_type,
        )
        if yf_price is not None:
            return yf_price

        # Fallback: IB direct quote
        try:
            from lumibot.entities import Asset

            option_asset = Asset(
                symbol=contract.underlying,
                asset_type=Asset.AssetType.OPTION,
                expiration=contract.expiration,
                strike=contract.strike,
                right=contract.option_type.lower(),
                multiplier=int(contract.multiplier),
            )
            price = self.get_last_price(option_asset)
            if price is not None:
                return float(price)
        except Exception as e:
            logger.debug("IB premium fetch failed: %s", e)

        return None

    # ---- Multi-ticker snapshot ----

    def get_multi_snapshot(self) -> dict:
        """Return snapshot covering all tickers."""
        # Primary snapshot from active trader
        snapshot = self.icc_trader.get_snapshot()
        snapshot["active_ticker"] = self._active_ticker
        snapshot["tickers"] = self._tickers
        snapshot["multi_ticker"] = self._multi_ticker

        # ORB state per ticker
        from icc.core.orb_strategy import ORBStrategyEngine
        ticker_states = {}
        for ticker in self._tickers:
            trader = self._traders[ticker]
            strat = trader.strategy
            ts: dict = {
                "fsm_state": trader.fsm.state.value,
                "candle_count": len(trader.buffer),
                "is_flat": trader.positions.is_flat,
            }
            if isinstance(strat, ORBStrategyEngine):
                ts["range_high"] = strat._range_high
                ts["range_low"] = strat._range_low
                ts["range_height"] = strat.range_height
                ts["armed_bars"] = strat._armed_bar_count
                ts["trade_taken"] = strat._trade_taken
            last = trader.buffer.last
            if last:
                ts["last_price"] = last.close
            ticker_states[ticker] = ts
        snapshot["ticker_states"] = ticker_states
        return snapshot

    # ---- Contract helpers ----

    @staticmethod
    def _front_month_expiration() -> date:
        """Return the 3rd Friday of the current front-month quarterly contract."""
        today = date.today()
        quarterly = [3, 6, 9, 12]

        for m in quarterly:
            y = today.year if m >= today.month else today.year + 1
            third_friday = _third_friday(y, m)
            if third_friday >= today:
                return third_friday

        return _third_friday(today.year + 1, 3)

    @staticmethod
    def _next_quarterly_expiration() -> date:
        """Return the next quarterly expiration strictly after today."""
        today = date.today()
        quarterly = [3, 6, 9, 12]
        for m in quarterly:
            y = today.year if m >= today.month else today.year + 1
            tf = _third_friday(y, m)
            if tf > today:
                return tf
        return _third_friday(today.year + 1, 3)


def _third_friday(year: int, month: int) -> date:
    """Return the 3rd Friday of the given month/year."""
    first = date(year, month, 1)
    days_to_friday = (4 - first.weekday()) % 7
    first_friday = first + timedelta(days=days_to_friday)
    return first_friday + timedelta(weeks=2)
