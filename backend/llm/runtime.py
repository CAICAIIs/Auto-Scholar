from __future__ import annotations

import logging
from dataclasses import dataclass

from backend.llm.providers import resolve_api_key
from backend.llm.router import get_fallback_chain, select_model
from backend.llm.task_types import TaskType
from backend.schemas import ModelConfig

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class RuntimeSelection:
    requested_model_id: str | None
    selected_model_id: str | None
    fallback_chain: list[str]
    task_type: TaskType | None


def build_runtime_selection(
    *,
    model_registry: dict[str, ModelConfig],
    requested_model_id: str | None,
    task_type_value: str | None,
) -> RuntimeSelection:
    task_type: TaskType | None = None
    selected_model_id = requested_model_id

    if task_type_value:
        try:
            task_type = TaskType(task_type_value)
        except ValueError:
            logger.warning("Unknown task_type=%s, using default model selection", task_type_value)
        else:
            selected_model_id = select_model(
                task_type,
                model_registry,
                override_model_id=requested_model_id,
            )

    fallback_chain: list[str] = []
    if task_type is not None:
        fallback_chain = get_fallback_chain(
            task_type,
            model_registry,
            primary_model_id=selected_model_id,
        )
    elif selected_model_id:
        fallback_chain = [selected_model_id]

    return RuntimeSelection(
        requested_model_id=requested_model_id,
        selected_model_id=selected_model_id,
        fallback_chain=fallback_chain,
        task_type=task_type,
    )


def resolve_model_config(
    *,
    model_registry: dict[str, ModelConfig],
    model_id: str | None,
) -> ModelConfig | None:
    if model_id and model_id in model_registry:
        return model_registry[model_id]
    return None
