"""AI Runtime Layer for Auto-Scholar.

Phase 1: Task-aware routing + Fallback + Model capability detection.
"""

from backend.llm.router import get_fallback_chain, select_model
from backend.llm.task_types import TaskRequirement, TaskType

__all__ = ["TaskRequirement", "TaskType", "get_fallback_chain", "select_model"]
