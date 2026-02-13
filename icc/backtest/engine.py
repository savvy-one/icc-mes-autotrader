"""BacktestEngine — historical replay loop."""

from __future__ import annotations

import logging

from icc.backtest.report import BacktestResult
from icc.broker.backtest import BacktestBrokerAdapter
from icc.config import AppSettings
from icc.core.trader import Trader
from icc.market.candle import Candle
from icc.market.feed import ReplayFeed
from icc.oms.manager import OrderManager

logger = logging.getLogger(__name__)


class BacktestEngine:
    def __init__(self, config: AppSettings, candles: list[Candle]):
        self.config = config
        self.candles = candles
        self.result = BacktestResult()

    def run(self) -> BacktestResult:
        broker = BacktestBrokerAdapter(
            slippage_ticks=self.config.risk.slippage_ticks,
            commission_per_side=self.config.risk.commission_per_side,
        )
        broker.connect()
        oms = OrderManager(broker)
        trader = Trader(config=self.config, order_manager=oms)

        feed = ReplayFeed(self.candles)
        equity = self.config.risk.account_size

        logger.info("Starting backtest with %d candles", len(self.candles))

        for candle in feed:
            trader.on_candle(candle)

            # Track equity
            unrealized = trader.positions.unrealized_pnl(candle.close)
            current_equity = equity + trader.positions.closed_pnl + unrealized
            self.result.equity_curve.append(current_equity)

            # Record completed trades
            if trader.risk.state.killed:
                logger.info("Kill switch activated, stopping backtest")
                break

        # Collect trade PnLs
        # The closed_pnl accumulates in the position tracker
        # We track individual trades through the risk engine state
        self.result.trades = self._extract_trade_pnls(trader)

        broker.disconnect()
        logger.info("Backtest complete: %s", self.result.summary())
        return self.result

    def _extract_trade_pnls(self, trader: Trader) -> list[float]:
        """Extract individual trade P&Ls from the position tracker's history.
        For MVP, we use the total closed PnL divided by trade count as approximation,
        unless we have detailed tracking."""
        total = trader.positions.closed_pnl
        count = trader._trade_count
        if count == 0:
            return []
        # Simple split — in production, log each trade individually
        avg = total / count
        return [avg] * count
