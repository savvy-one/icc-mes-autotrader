"""AlertChannel ABC + AlertRouter."""

from __future__ import annotations

import logging
from abc import ABC, abstractmethod

logger = logging.getLogger(__name__)


class AlertChannel(ABC):
    @abstractmethod
    def send(self, alert_type: str, message: str) -> bool:
        """Send an alert. Returns True if successful."""


class AlertRouter:
    """Routes alerts to all registered channels."""

    def __init__(self) -> None:
        self._channels: list[AlertChannel] = []

    def add_channel(self, channel: AlertChannel) -> None:
        self._channels.append(channel)

    def send(self, alert_type: str, message: str) -> None:
        for channel in self._channels:
            try:
                channel.send(alert_type, message)
            except Exception as e:
                logger.error("Alert channel %s failed: %s", type(channel).__name__, e)
