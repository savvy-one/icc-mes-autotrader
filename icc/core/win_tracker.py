"""WinRateTracker — rolling and overall win rate with confidence adjustment."""

from __future__ import annotations

from collections import deque


class WinRateTracker:
    def __init__(self, window: int = 20):
        self._window = window
        self._results: deque[float] = deque(maxlen=window)
        self._total_wins = 0
        self._total_losses = 0

    def record(self, pnl: float) -> None:
        self._results.append(pnl)
        if pnl > 0:
            self._total_wins += 1
        elif pnl < 0:
            self._total_losses += 1

    @property
    def rolling_win_rate(self) -> float | None:
        if not self._results:
            return None
        wins = sum(1 for p in self._results if p > 0)
        return wins / len(self._results)

    @property
    def overall_win_rate(self) -> float | None:
        total = self._total_wins + self._total_losses
        if total == 0:
            return None
        return self._total_wins / total

    @property
    def confidence_adjustment(self) -> float:
        """Return multiplier for research confidence based on recent performance."""
        wr = self.rolling_win_rate
        if wr is None:
            return 1.0
        if wr >= 0.8:
            return 1.1
        if wr < 0.4:
            return 0.7
        return 1.0

    def get_snapshot(self) -> dict:
        return {
            "rolling_win_rate": self.rolling_win_rate,
            "overall_win_rate": self.overall_win_rate,
            "rolling_window": self._window,
            "recent_count": len(self._results),
            "total_wins": self._total_wins,
            "total_losses": self._total_losses,
            "confidence_adj": self.confidence_adjustment,
        }
