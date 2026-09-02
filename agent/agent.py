"""
agent.py — Module 2: Synchronisation agent entry point.

Starts the filesystem watcher on SYNC_FOLDER and runs until interrupted
(Ctrl-C or SIGTERM).

In this M2 implementation the agent uses ``LoggingEventSender`` — events are
logged to stdout rather than sent to a real M3 backend.  When M3 is
implemented, replace ``LoggingEventSender`` with the HTTP sender without
modifying this file or watcher.py.

Usage:
    python -m agent.agent
    # or
    python agent/agent.py
"""

from __future__ import annotations

import logging
import signal
import sys
import time

from agent.config import SYNC_FOLDER
from agent.sender import LoggingEventSender
from agent.watcher import SyncWatcher

logger = logging.getLogger(__name__)


def _handle_signal(signum: int, frame) -> None:  # noqa: ANN001
    """Raise KeyboardInterrupt on SIGTERM so the finally block runs cleanly."""
    raise KeyboardInterrupt(f"Signal {signum} received")


def main() -> int:
    signal.signal(signal.SIGTERM, _handle_signal)

    logger.info("=== Synchronisation Agent (Module 2) starting ===")
    logger.info("Watching: %s", SYNC_FOLDER)
    logger.info("Sender: LoggingEventSender (M3 not yet implemented)")

    sender = LoggingEventSender()
    watcher = SyncWatcher(sync_folder=SYNC_FOLDER, sender=sender)

    try:
        watcher.start()
        while True:
            time.sleep(1)
    except FileNotFoundError as exc:
        logger.error("Cannot start watcher: %s", exc)
        return 1
    except KeyboardInterrupt:
        logger.info("Shutdown requested — stopping watcher...")
    finally:
        watcher.stop()

    logger.info("=== Synchronisation Agent stopped ===")
    return 0


if __name__ == "__main__":
    sys.exit(main())
