"""Core configuration and utilities."""

from backend.core.config import Settings, get_settings
from backend.core.lifecycle import (
    DEPENDENCY_CHECK_TIMEOUT_SECONDS,
    SHUTDOWN_SSE_WAIT_SECONDS,
    SHUTDOWN_TASK_TIMEOUT_SECONDS,
    SHUTDOWN_TOTAL_TIMEOUT_SECONDS,
    cancel_background_tasks,
    check_dependency_health,
    get_active_sse_streams,
    get_shutdown_event,
    is_shutting_down,
    register_signal_handlers,
    run_cleanup_sequence,
    track_background_task,
)

__all__ = [
    "Settings",
    "get_settings",
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
