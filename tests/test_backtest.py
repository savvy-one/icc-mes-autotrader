"""Tests for backtest engine and report."""

from datetime import datetime, timedelta

import pytest

from icc.backtest.engine import BacktestEngine
from icc.backtest.report import BacktestResult
from icc.config import AppSettings
from icc.market.candle import Candle


class TestBacktestResult:
    def test_empty(self):
        r = BacktestResult()
        assert r.total_pnl == 0.0
        assert r.trade_count == 0
        assert r.win_rate == 0.0

    def test_with_trades(self):
        r = BacktestResult(trades=[10.0, -5.0, 15.0, -3.0])
        assert r.total_pnl == pytest.approx(17.0)
        assert r.trade_count == 4
        assert r.win_count == 2
        assert r.loss_count == 2
        assert r.win_rate == pytest.approx(0.5)

    def test_profit_factor(self):
        r = BacktestResult(trades=[10.0, -5.0])
        assert r.profit_factor == pytest.approx(2.0)

    def test_profit_factor_no_losses(self):
        r = BacktestResult(trades=[10.0, 5.0])
        assert r.profit_factor == float("inf")

    def test_max_drawdown(self):
        r = BacktestResult(equity_curve=[100, 110, 105, 108, 95, 100])
        assert r.max_drawdown == pytest.approx(15.0)  # 110 -> 95

    def test_summary_keys(self):
        r = BacktestResult(trades=[10.0])
        s = r.summary()
        assert "total_pnl" in s
        assert "sharpe_ratio" in s


class TestBacktestEngine:
    def test_runs_without_error(self):
        config = AppSettings()
        base = datetime(2024, 1, 2, 9, 30)
        # Build enough candles for indicators to warm up
        candles = []
        for i in range(50):
            price = 100.0 + i * 0.1
            candles.append(Candle(
                timestamp=base + timedelta(minutes=i),
                open=price - 0.05,
                high=price + 0.5,
                low=price - 0.5,
                close=price,
                volume=1000,
            ))
        engine = BacktestEngine(config, candles)
        result = engine.run()
        assert isinstance(result, BacktestResult)
        assert len(result.equity_curve) == 50
