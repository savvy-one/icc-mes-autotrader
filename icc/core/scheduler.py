"""SessionScheduler — APScheduler cron jobs for auto-start/stop trading sessions."""

from __future__ import annotations

import logging
from datetime import datetime
from typing import TYPE_CHECKING, Any

from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger

if TYPE_CHECKING:
    from icc.web.trading_session import TradingSession

logger = logging.getLogger(__name__)

# Session window defaults (ET)
DEFAULT_OPEN_HOUR = 9
DEFAULT_OPEN_MINUTE = 30
DEFAULT_CLOSE_HOUR = 11
DEFAULT_CLOSE_MINUTE = 0


class SessionScheduler:
    """Manages cron-based auto-start and auto-stop of trading sessions.

    Runs two weekday cron jobs in US/Eastern timezone:
    - session_open: calls session.start_live() at 9:30 ET
    - session_close: calls session.flatten_and_stop() at 11:00 ET
    """

    def __init__(
        self,
        session: TradingSession,
        open_hour: int = DEFAULT_OPEN_HOUR,
        open_minute: int = DEFAULT_OPEN_MINUTE,
        close_hour: int = DEFAULT_CLOSE_HOUR,
        close_minute: int = DEFAULT_CLOSE_MINUTE,
    ) -> None:
        self._session = session
        self._open_hour = open_hour
        self._open_minute = open_minute
        self._close_hour = close_hour
        self._close_minute = close_minute
        self._scheduler = BackgroundScheduler(timezone="US/Eastern")

    def start(self) -> None:
        """Start the scheduler with open/close cron jobs."""
        self._scheduler.add_job(
            self._session_open,
            CronTrigger(
                day_of_week="mon-fri",
                hour=self._open_hour,
                minute=self._open_minute,
                timezone="US/Eastern",
            ),
            id="session_open",
            replace_existing=True,
        )
        self._scheduler.add_job(
            self._session_close,
            CronTrigger(
                day_of_week="mon-fri",
                hour=self._close_hour,
                minute=self._close_minute,
                timezone="US/Eastern",
            ),
            id="session_close",
            replace_existing=True,
        )
        self._scheduler.start()
        logger.info(
            "SessionScheduler started: open=%02d:%02d, close=%02d:%02d ET",
            self._open_hour,
            self._open_minute,
            self._close_hour,
            self._close_minute,
        )

    def stop(self) -> None:
        """Shut down the scheduler."""
        self._scheduler.shutdown(wait=False)
        logger.info("SessionScheduler stopped")

    def _session_open(self) -> None:
        """Cron callback: start the live trading session."""
        logger.info("Scheduler: opening trading session")
        try:
            self._session.start_live()
        except RuntimeError as e:
            logger.error("Scheduler: failed to start session: %s", e)

    def _session_close(self) -> None:
        """Cron callback: flatten positions and stop the session."""
        logger.info("Scheduler: closing trading session")
        try:
            self._session.flatten_and_stop()
        except Exception as e:
            logger.error("Scheduler: failed to stop session: %s", e)

    def get_status(self) -> dict[str, Any]:
        """Return scheduler status including next fire times."""
        status: dict[str, Any] = {"running": self._scheduler.running}
        for job_id in ("session_open", "session_close"):
            job = self._scheduler.get_job(job_id)
            if job and job.next_run_time:
                status[f"next_{job_id}"] = job.next_run_time.isoformat()
            else:
                status[f"next_{job_id}"] = None
        return status
