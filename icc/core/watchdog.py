"""Watchdog — monitors candle flow health, warns on stale data, auto-restarts."""

from __future__ import annotations

import logging
import threading
import time
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from icc.web.trading_session import TradingSession

logger = logging.getLogger(__name__)

# Thresholds in seconds
WARN_AFTER = 180  # 3 minutes
RESTART_AFTER = 300  # 5 minutes
CHECK_INTERVAL = 30  # check every 30s
MAX_RESTARTS_PER_DAY = 3


class Watchdog:
    """Background health monitor for live trading sessions.

    Tracks the last candle timestamp and:
    - Warns after WARN_AFTER seconds of silence
    - Attempts session restart after RESTART_AFTER seconds
    - Limits restart attempts to MAX_RESTARTS_PER_DAY per session day
    """

    def __init__(self, session: TradingSession) -> None:
        self._session = session
        self._last_candle_time: float = 0.0
        self._restart_count = 0
        self._stop_event = threading.Event()
        self._thread: threading.Thread | None = None
        self._warned = False

    def start(self) -> None:
        """Start the watchdog monitoring thread."""
        self._last_candle_time = time.time()
        self._restart_count = 0
        self._warned = False
        self._stop_event.clear()
        self._thread = threading.Thread(target=self._monitor_loop, daemon=True)
        self._thread.start()
        logger.info("Watchdog started (warn=%ds, restart=%ds)", WARN_AFTER, RESTART_AFTER)

    def stop(self) -> None:
        """Stop the watchdog."""
        self._stop_event.set()
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=5.0)
        self._thread = None
        logger.info("Watchdog stopped")

    def record_candle(self) -> None:
        """Called when a candle event is observed — resets the silence timer."""
        self._last_candle_time = time.time()
        self._warned = False

    def _monitor_loop(self) -> None:
        """Check candle freshness every CHECK_INTERVAL seconds."""
        while not self._stop_event.is_set():
            self._stop_event.wait(CHECK_INTERVAL)
            if self._stop_event.is_set():
                break

            if not self._session.is_running:
                continue

            silence = time.time() - self._last_candle_time

            if silence >= RESTART_AFTER:
                self._attempt_restart()
            elif silence >= WARN_AFTER and not self._warned:
                logger.warning(
                    "Watchdog: no candles for %.0fs — possible connection issue", silence
                )
                self._warned = True

    def _attempt_restart(self) -> None:
        """Attempt to restart the trading session after prolonged silence."""
        if self._restart_count >= MAX_RESTARTS_PER_DAY:
            logger.error(
                "Watchdog: max restarts (%d) reached for today — not restarting",
                MAX_RESTARTS_PER_DAY,
            )
            return

        self._restart_count += 1
        logger.warning(
            "Watchdog: attempting restart %d/%d after prolonged silence",
            self._restart_count,
            MAX_RESTARTS_PER_DAY,
        )

        try:
            self._session.stop()
            self._stop_event.wait(5.0)  # pause before restart
            if not self._stop_event.is_set():
                self._session.start_live()
                self._last_candle_time = time.time()
                self._warned = False
                logger.info("Watchdog: session restarted successfully")
        except Exception as e:
            logger.error("Watchdog: restart failed: %s", e)
