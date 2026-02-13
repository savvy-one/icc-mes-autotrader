"""BacktestResult — Sharpe, drawdown, win rate, P&L."""

from __future__ import annotations

from dataclasses import dataclass, field
import math


@dataclass
class BacktestResult:
    trades: list[float] = field(default_factory=list)  # list of trade P&Ls
    equity_curve: list[float] = field(default_factory=list)

    @property
    def total_pnl(self) -> float:
        return sum(self.trades)

    @property
    def trade_count(self) -> int:
        return len(self.trades)

    @property
    def win_count(self) -> int:
        return sum(1 for t in self.trades if t > 0)

    @property
    def loss_count(self) -> int:
        return sum(1 for t in self.trades if t <= 0)

    @property
    def win_rate(self) -> float:
        if not self.trades:
            return 0.0
        return self.win_count / self.trade_count

    @property
    def avg_win(self) -> float:
        wins = [t for t in self.trades if t > 0]
        return sum(wins) / len(wins) if wins else 0.0

    @property
    def avg_loss(self) -> float:
        losses = [t for t in self.trades if t <= 0]
        return sum(losses) / len(losses) if losses else 0.0

    @property
    def profit_factor(self) -> float:
        gross_profit = sum(t for t in self.trades if t > 0)
        gross_loss = abs(sum(t for t in self.trades if t < 0))
        if gross_loss == 0:
            return float("inf") if gross_profit > 0 else 0.0
        return gross_profit / gross_loss

    @property
    def max_drawdown(self) -> float:
        if not self.equity_curve:
            return 0.0
        peak = self.equity_curve[0]
        max_dd = 0.0
        for eq in self.equity_curve:
            if eq > peak:
                peak = eq
            dd = peak - eq
            if dd > max_dd:
                max_dd = dd
        return max_dd

    @property
    def sharpe_ratio(self) -> float:
        """Annualized Sharpe ratio (assumes daily returns, 252 trading days)."""
        if len(self.trades) < 2:
            return 0.0
        mean = sum(self.trades) / len(self.trades)
        variance = sum((t - mean) ** 2 for t in self.trades) / (len(self.trades) - 1)
        std = math.sqrt(variance)
        if std == 0:
            return 0.0
        return (mean / std) * math.sqrt(252)

    def summary(self) -> dict:
        return {
            "total_pnl": round(self.total_pnl, 2),
            "trade_count": self.trade_count,
            "win_rate": round(self.win_rate * 100, 1),
            "avg_win": round(self.avg_win, 2),
            "avg_loss": round(self.avg_loss, 2),
            "profit_factor": round(self.profit_factor, 2),
            "max_drawdown": round(self.max_drawdown, 2),
            "sharpe_ratio": round(self.sharpe_ratio, 2),
        }
