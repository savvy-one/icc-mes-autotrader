"""SMTP email alerts."""

from __future__ import annotations

import logging
import smtplib
from email.mime.text import MIMEText

from icc.alerts.base import AlertChannel
from icc.config import AlertConfig

logger = logging.getLogger(__name__)


class EmailAlertChannel(AlertChannel):
    def __init__(self, config: AlertConfig):
        self.config = config

    def send(self, alert_type: str, message: str) -> bool:
        if not self.config.email_to or not self.config.smtp_user:
            logger.warning("Email alert not configured")
            return False

        msg = MIMEText(message)
        msg["Subject"] = f"ICC AutoTrader Alert: {alert_type.upper()}"
        msg["From"] = self.config.smtp_user
        msg["To"] = self.config.email_to

        try:
            with smtplib.SMTP(self.config.smtp_host, self.config.smtp_port) as server:
                server.starttls()
                server.login(self.config.smtp_user, self.config.smtp_pass)
                server.send_message(msg)
            logger.info("Email alert sent: %s", alert_type)
            return True
        except Exception as e:
            logger.error("Email alert failed: %s", e)
            return False
