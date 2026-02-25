from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from typing import Literal

CostTier = Literal["low", "medium", "high"]


class TaskType(StrEnum):
    PLANNING = "planning"
    EXTRACTION = "extraction"
    WRITING = "writing"
    QA = "qa"
    REFLECTION = "reflection"


@dataclass(frozen=True)
class TaskRequirement:
    needs_reasoning: bool = False
    needs_structured_output: bool = False
    needs_long_context: bool = False
    prefers_creativity: bool = False
    max_cost_tier: CostTier = "high"
    latency_sensitive: bool = False


TASK_REQUIREMENTS: dict[TaskType, TaskRequirement] = {
    TaskType.PLANNING: TaskRequirement(
        needs_reasoning=True,
        needs_structured_output=True,
        max_cost_tier="high",
    ),
    TaskType.EXTRACTION: TaskRequirement(
        needs_structured_output=True,
        max_cost_tier="medium",
        latency_sensitive=True,
    ),
    TaskType.WRITING: TaskRequirement(
        needs_long_context=True,
        prefers_creativity=True,
        max_cost_tier="high",
    ),
    TaskType.QA: TaskRequirement(
        needs_structured_output=True,
        max_cost_tier="low",
        latency_sensitive=True,
    ),
    TaskType.REFLECTION: TaskRequirement(
        needs_reasoning=True,
        needs_structured_output=True,
        max_cost_tier="medium",
    ),
}


def get_task_requirement(task_type: TaskType) -> TaskRequirement:
    return TASK_REQUIREMENTS[task_type]
