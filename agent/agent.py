"""
agent.py — Module 2: Synchronisation agent entry point.

Starts the filesystem watcher on SYNC_FOLDER and runs until interrupted
(Ctrl-C or SIGTERM).

If ``BACKEND_URL`` is set, events are sent with ``HttpEventSender``.
Otherwise the agent falls back to ``LoggingEventSender`` so M2 can still
run without a backend.

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

from agent.config import BACKEND_URL, SYNC_FOLDER
from agent.http_sender import HttpEventSender
from agent.sender import LoggingEventSender
from agent.watcher import SyncWatcher

logger = logging.getLogger(__name__)


def _handle_signal(signum: int, frame) -> None:  # noqa: ANN001
    """Raise KeyboardInterrupt on SIGTERM so the finally block runs cleanly."""
    raise KeyboardInterrupt(f"Signal {signum} received")


def main() -> int:
    signal.signal(signal.SIGTERM, _handle_signal)

    logger.info("=== Synchronisation Agent starting ===")
    logger.info("Watching: %s", SYNC_FOLDER)

    if BACKEND_URL:
        logger.info("Sender: HttpEventSender -> %s", BACKEND_URL)
        sender = HttpEventSender(backend_url=BACKEND_URL, sync_folder=SYNC_FOLDER)
    else:
        logger.info("Sender: LoggingEventSender (BACKEND_URL not set)")
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
