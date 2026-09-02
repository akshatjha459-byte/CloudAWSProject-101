"""
sender.py — Module 2: Abstract event sender interface.

Defines the interface that the agent uses to dispatch ``SyncEvent`` objects
to an upstream consumer (Module 3 — FastAPI backend).

This module provides:
  - ``EventSender``: the abstract base class used by the watcher.
  - ``LoggingEventSender``: a development stub that logs events.

The HTTP implementation lives in ``agent.http_sender.HttpEventSender`` (M3).
The watcher is coded against the abstract interface.
"""

from __future__ import annotations

import abc
import logging

from agent.events import SyncEvent

logger = logging.getLogger(__name__)


class EventSender(abc.ABC):
    """Abstract base class for dispatching synchronisation events to M3.

    Implementors must provide :meth:`send`.
    """

    @abc.abstractmethod
    def send(self, event: SyncEvent) -> None:
        """Dispatch *event* to the upstream consumer.

        Implementations should not raise on transient failures; instead they
        should log the error and, where appropriate, queue the event for retry.

        Args:
            event: The normalised synchronisation event to dispatch.
        """


class LoggingEventSender(EventSender):
    """Development/test sender that logs events instead of sending them over HTTP.

    This is the default sender used when M3 is unavailable.  It allows the
    agent to run and produce verifiable output without a backend server.
    """

    def send(self, event: SyncEvent) -> None:
        """Log the event as a JSON string at INFO level."""
        logger.info("EVENT: %s", event.to_json())
