"""Application lifecycle management.

Handles startup, shutdown, signal handling, and background task tracking.
"""

import asyncio
import logging
import signal
import time
from ctypes import c_bool
from typing import Any

from backend.utils.clients import cleanup_clients
from backend.utils.http_pool import close_session
from backend.utils.llm_client import cleanup_llm_clients

try:
    from backend.db.engine import dispose_engine
except Exception:  # pragma: no cover
    dispose_engine = None

logger = logging.getLogger(__name__)

# Shutdown configuration
SHUTDOWN_TASK_TIMEOUT_SECONDS = 30
SHUTDOWN_TOTAL_TIMEOUT_SECONDS = 45
SHUTDOWN_SSE_WAIT_SECONDS = 10
DEPENDENCY_CHECK_TIMEOUT_SECONDS = 0.5

# Global state
_shutdown_event = asyncio.Event()
is_shutting_down = c_bool(False)
_background_tasks: set[asyncio.Task[Any]] = set()
_active_sse_streams: set[str] = set()


async def check_dependency_health(
    dependency_name: str,
    check_fn: Any,
    timeout_seconds: float = DEPENDENCY_CHECK_TIMEOUT_SECONDS,
) -> tuple[bool, str | None]:
    """Check if a dependency is healthy.

    Args:
        dependency_name: Name of the dependency for logging
        check_fn: Async function to call for health check
        timeout_seconds: Timeout for the check

    Returns:
        Tuple of (is_healthy, error_message)
    """
    try:
        await asyncio.wait_for(check_fn(), timeout=timeout_seconds)
        return True, None
    except Exception as exc:
        logger.warning("Dependency check failed for %s: %s", dependency_name, exc)
        return False, str(exc)


def register_signal_handlers() -> None:
    """Register SIGTERM and SIGINT handlers for graceful shutdown."""

    def _handle_signal(signum: int, _frame: Any) -> None:
        if is_shutting_down.value:
            return
        is_shutting_down.value = True
        _shutdown_event.set()
        logger.info("Received signal %s, initiating graceful shutdown", signum)

    signal.signal(signal.SIGTERM, _handle_signal)
    signal.signal(signal.SIGINT, _handle_signal)


def track_background_task(task: asyncio.Task[Any]) -> None:
    """Track a background task for graceful shutdown.

    Args:
        task: The asyncio task to track
    """
    _background_tasks.add(task)
    task.add_done_callback(_background_tasks.discard)


async def cancel_background_tasks() -> None:
    """Cancel all tracked background tasks."""
    if not _background_tasks:
        logger.info("No background tasks to cancel")
        return

    logger.info("Cancelling %d background tasks", len(_background_tasks))
    for task in list(_background_tasks):
        task.cancel()

    done, pending = await asyncio.wait(_background_tasks, timeout=SHUTDOWN_TASK_TIMEOUT_SECONDS)
    logger.info("Background task cancellation result: done=%d pending=%d", len(done), len(pending))
    for task in pending:
        logger.warning("Background task did not finish before timeout: %s", task)


async def run_cleanup_sequence() -> None:
    """Execute the full cleanup sequence during shutdown."""
    start_ts = time.perf_counter()
    logger.info("Graceful shutdown cleanup started at %.3f", start_ts)

    logger.info("Cleanup step: stop accepting new work")
    is_shutting_down.value = True
    _shutdown_event.set()

    logger.info("Cleanup step: wait for active SSE streams to finish")
    if _active_sse_streams:
        logger.info("Waiting for %d active SSE streams to finish", len(_active_sse_streams))
        for i in range(int(SHUTDOWN_SSE_WAIT_SECONDS * 2)):
            if not _active_sse_streams:
                logger.info("All SSE streams finished gracefully")
                break
            await asyncio.sleep(0.5)
        if _active_sse_streams:
            logger.warning(
                "Forcing shutdown with %d active streams: %s",
                len(_active_sse_streams),
                list(_active_sse_streams),
            )

    logger.info("Cleanup step: cancel background tasks")
    await cancel_background_tasks()

    logger.info("Cleanup step: cleanup vector/db clients")
    await cleanup_clients()

    logger.info("Cleanup step: cleanup LLM clients")
    await cleanup_llm_clients()

    if dispose_engine is not None:
        logger.info("Cleanup step: dispose SQLAlchemy engine")
        await dispose_engine()
    else:
        logger.info("Cleanup step: dispose SQLAlchemy engine skipped (not available)")

    logger.info("Cleanup step: close shared HTTP session")
    await close_session()

    elapsed = time.perf_counter() - start_ts
    logger.info("Graceful shutdown cleanup completed in %.3fs", elapsed)
    if elapsed > SHUTDOWN_TOTAL_TIMEOUT_SECONDS:
        logger.warning(
            "Graceful shutdown exceeded target (%ss): %.3fs",
            SHUTDOWN_TOTAL_TIMEOUT_SECONDS,
            elapsed,
        )


def get_active_sse_streams() -> set[str]:
    """Get the set of active SSE stream IDs."""
    return _active_sse_streams


def get_shutdown_event() -> asyncio.Event:
    """Get the shutdown event."""
    return _shutdown_event


__all__ = [
    "SHUTDOWN_TASK_TIMEOUT_SECONDS",
    "SHUTDOWN_TOTAL_TIMEOUT_SECONDS",
    "SHUTDOWN_SSE_WAIT_SECONDS",
    "DEPENDENCY_CHECK_TIMEOUT_SECONDS",
    "is_shutting_down",
    "check_dependency_health",
    "register_signal_handlers",
    "track_background_task",
    "cancel_background_tasks",
    "run_cleanup_sequence",
    "get_active_sse_streams",
    "get_shutdown_event",
]
