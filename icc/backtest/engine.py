"""BacktestEngine — historical replay loop."""

from __future__ import annotations

import logging
from datetime import date

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

        # Set up option chain resolver for OPTIONS mode
        option_chain_resolver = None
        premium_calc = None
        if self.config.options.instrument_type == "OPTIONS":
            from icc.backtest.premium import SyntheticPremiumCalculator
            from icc.broker.option_chain import (
                MockOptionChainProvider,
                OptionChainResolver,
            )

            premium_calc = SyntheticPremiumCalculator(vol=0.20)
            # Build a synthetic provider that generates chains on-the-fly
            provider = _SyntheticOptionProvider(
                premium_calc=premium_calc,
                underlying=self.config.options.underlying,
                strike_spacing=5.0,
                num_strikes=11,
            )
            option_chain_resolver = OptionChainResolver(
                provider=provider,
                underlying=self.config.options.underlying,
                strike_mode=self.config.options.strike_mode,
                expiration_mode=self.config.options.expiration_mode,
                expiration_guard_minutes=self.config.options.expiration_guard_minutes,
                max_premium=self.config.options.max_premium,
                otm_fallback=self.config.options.otm_fallback,
            )

        trader = Trader(
            config=self.config,
            order_manager=oms,
            option_chain_resolver=option_chain_resolver,
        )

        feed = ReplayFeed(self.candles)
        equity = self.config.risk.account_size

        logger.info("Starting backtest with %d candles", len(self.candles))

        for candle in feed:
            # Update the synthetic provider's reference price for chain generation
            if self.config.options.instrument_type == "OPTIONS" and hasattr(trader, '_active_contract'):
                self._update_synthetic_provider(trader, candle, premium_calc)

            trader.on_candle(candle)

            # Track equity — for options, use synthetic premium for unrealized
            if (
                premium_calc is not None
                and trader._active_contract is not None
                and not trader.positions.is_flat
            ):
                contract = trader._active_contract
                dte = max(0, (contract.expiration - candle.timestamp.date()).days)
                current_premium = premium_calc.premium(
                    candle.close, contract.strike, float(dte), contract.option_type,
                )
                unrealized = trader.positions.unrealized_pnl(current_premium)
            else:
                unrealized = trader.positions.unrealized_pnl(candle.close)

            current_equity = equity + trader.positions.closed_pnl + unrealized
            self.result.equity_curve.append(current_equity)

            if trader.risk.state.killed:
                logger.info("Kill switch activated, stopping backtest")
                break

        self.result.trades = self._extract_trade_pnls(trader)

        broker.disconnect()
        logger.info("Backtest complete: %s", self.result.summary())
        return self.result

    def _update_synthetic_provider(self, trader, candle, premium_calc):
        """Keep the synthetic provider's reference price in sync with candles."""
        # The provider needs the current candle date for DTE calculations
        if hasattr(trader, '_option_resolver') and trader._option_resolver is not None:
            provider = trader._option_resolver._provider
            if isinstance(provider, _SyntheticOptionProvider):
                provider.set_reference(candle.close, candle.timestamp.date())

    def _extract_trade_pnls(self, trader: Trader) -> list[float]:
        """Extract individual trade P&Ls from the position tracker's history.
        For MVP, we use the total closed PnL divided by trade count as approximation,
        unless we have detailed tracking."""
        total = trader.positions.closed_pnl
        count = trader._trade_count
        if count == 0:
            return []
        avg = total / count
        return [avg] * count


class _SyntheticOptionProvider:
    """Generates synthetic option chains using Black-Scholes for backtesting."""

    def __init__(
        self,
        premium_calc,
        underlying: str = "MES",
        strike_spacing: float = 5.0,
        num_strikes: int = 11,
    ) -> None:
        self._calc = premium_calc
        self._underlying = underlying
        self._strike_spacing = strike_spacing
        self._num_strikes = num_strikes
        self._ref_price: float = 5000.0
        self._ref_date: date = date.today()

    def set_reference(self, price: float, as_of: date) -> None:
        """Update reference price and date for chain generation."""
        self._ref_price = price
        self._ref_date = as_of

    def get_option_expirations(self, underlying: str) -> list[date]:
        """Return synthetic expirations: today + weekly + monthly."""
        from datetime import timedelta

        today = self._ref_date
        expirations = [today]  # 0DTE

        # Next 4 weekly expirations (Fridays)
        days_to_friday = (4 - today.weekday()) % 7
        if days_to_friday == 0:
            days_to_friday = 7
        for i in range(4):
            expirations.append(today + timedelta(days=days_to_friday + 7 * i))

        # Monthly (3rd Friday of next month)
        month = today.month + 1 if today.month < 12 else 1
        year = today.year if today.month < 12 else today.year + 1
        first = date(year, month, 1)
        days_to_fri = (4 - first.weekday()) % 7
        third_friday = first + timedelta(days=days_to_fri + 14)
        expirations.append(third_friday)

        return sorted(set(expirations))

    def get_option_chain(self, underlying: str, expiration: date) -> list[date]:
        """Generate a synthetic chain centered on the current price."""
        dte = max(0, (expiration - self._ref_date).days)
        center = round(self._ref_price / self._strike_spacing) * self._strike_spacing
        half = self._num_strikes // 2

        chain = []
        for i in range(-half, half + 1):
            strike = center + i * self._strike_spacing
            for opt_type in ("CALL", "PUT"):
                prem = self._calc.premium(self._ref_price, strike, float(dte), opt_type)
                delta = self._calc.delta(self._ref_price, strike, float(dte), opt_type)
                chain.append({
                    "strike": strike,
                    "option_type": opt_type,
                    "ask": round(prem * 1.02, 4),  # 2% spread
                    "bid": round(prem * 0.98, 4),
                    "last": round(prem, 4),
                    "delta": round(delta, 4),
                })
        return chain
