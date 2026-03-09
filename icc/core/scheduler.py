"""SessionScheduler — APScheduler cron jobs for auto-start/stop trading sessions.

Includes a catch-up interval job that runs every 2 minutes during weekday
trading hours.  If the cron trigger misfires (daemon-thread starvation under
uvicorn), the catch-up detects that no session is running and starts one.
"""

from __future__ import annotations

import logging
from datetime import datetime, time
from typing import TYPE_CHECKING, Any

import pytz
from apscheduler.events import EVENT_JOB_MISSED
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.interval import IntervalTrigger

if TYPE_CHECKING:
    from apscheduler.events import JobEvent
    from icc.web.trading_session import TradingSession

logger = logging.getLogger(__name__)

# Session window defaults (ET)
DEFAULT_OPEN_HOUR = 9
DEFAULT_OPEN_MINUTE = 30
DEFAULT_CLOSE_HOUR = 15
DEFAULT_CLOSE_MINUTE = 0

_ET = pytz.timezone("US/Eastern")

# Misfire grace wide enough to cover the full trading window so a late
# daemon-thread wake-up still executes the job rather than silently dropping it.
_TRADING_WINDOW_GRACE = 19800  # 5.5 hours in seconds


class SessionScheduler:
    """Manages cron-based auto-start and auto-stop of trading sessions.

    Runs three jobs in US/Eastern timezone:
    - session_open:  cron at open time (default 9:30 ET, weekdays)
    - session_close: cron at close time (default 15:00 ET, weekdays)
    - catch_up:      interval every 2 min — if within trading window and no
                     session running, starts one (guards against cron misfire)
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
        self._open_time = time(open_hour, open_minute)
        self._close_time = time(close_hour, close_minute)
        self._scheduler = BackgroundScheduler(timezone="US/Eastern")

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    def start(self) -> None:
        """Start the scheduler with open/close cron jobs + catch-up check."""
        # Listen for misfires so they appear in logs instead of vanishing.
        self._scheduler.add_listener(self._on_misfire, EVENT_JOB_MISSED)

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
            misfire_grace_time=_TRADING_WINDOW_GRACE,
            coalesce=True,
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
            misfire_grace_time=_TRADING_WINDOW_GRACE,
            coalesce=True,
        )
        # Catch-up: every 2 minutes, start a session if we're inside the
        # trading window and nothing is running.
        self._scheduler.add_job(
            self._catch_up_check,
            IntervalTrigger(minutes=2, timezone="US/Eastern"),
            id="catch_up",
            replace_existing=True,
            misfire_grace_time=120,
            coalesce=True,
        )
        self._scheduler.start()
        logger.info(
            "SessionScheduler started: open=%02d:%02d, close=%02d:%02d ET "
            "(catch-up every 2 min)",
            self._open_hour,
            self._open_minute,
            self._close_hour,
            self._close_minute,
        )

    def stop(self) -> None:
        """Shut down the scheduler."""
        self._scheduler.shutdown(wait=False)
        logger.info("SessionScheduler stopped")

    # ------------------------------------------------------------------
    # Job callbacks
    # ------------------------------------------------------------------

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

    def _catch_up_check(self) -> None:
        """Interval callback: start session if inside trading window and idle."""
        now_et = datetime.now(_ET)
        # Weekdays only (Monday=0 … Friday=4)
        if now_et.weekday() > 4:
            return
        current_time = now_et.time()
        if current_time < self._open_time or current_time >= self._close_time:
            return
        if self._session.is_running:
            return
        logger.warning(
            "Scheduler: catch-up check — no session running at %s ET, starting",
            now_et.strftime("%H:%M:%S"),
        )
        try:
            self._session.start_live()
        except RuntimeError as e:
            logger.error("Scheduler: catch-up failed to start session: %s", e)

    # ------------------------------------------------------------------
    # Misfire listener
    # ------------------------------------------------------------------

    def _on_misfire(self, event: JobEvent) -> None:
        """Log when APScheduler silently drops a job due to misfire."""
        logger.warning(
            "Scheduler: job '%s' MISFIRED (scheduled_run_time=%s)",
            event.job_id,
            getattr(event, "scheduled_run_time", "unknown"),
        )

    # ------------------------------------------------------------------
    # Status
    # ------------------------------------------------------------------

    def get_status(self) -> dict[str, Any]:
        """Return scheduler status including next fire times."""
        status: dict[str, Any] = {"running": self._scheduler.running}
        for job_id in ("session_open", "session_close", "catch_up"):
            job = self._scheduler.get_job(job_id)
            if job and job.next_run_time:
                status[f"next_{job_id}"] = job.next_run_time.isoformat()
            else:
                status[f"next_{job_id}"] = None
        return status
