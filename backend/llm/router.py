from __future__ import annotations

import logging

from backend.llm.task_types import TASK_REQUIREMENTS, TaskType
from backend.schemas import CostTier, ModelConfig

logger = logging.getLogger(__name__)

_COST_TIER_MAP: dict[str, CostTier] = {
    "low": CostTier.LOW,
    "medium": CostTier.MEDIUM,
    "high": CostTier.HIGH,
}


def _cost_allowed(model_cost: CostTier, max_cost: str) -> bool:
    max_rank = _COST_TIER_MAP[max_cost]
    return model_cost <= max_rank


def _score_model(model: ModelConfig, task_type: TaskType) -> float:
    req = TASK_REQUIREMENTS[task_type]
    score = 0.0

    if req.needs_reasoning:
        score += model.reasoning_score * 2.0
    if req.prefers_creativity:
        score += model.creativity_score * 1.5
    if req.latency_sensitive:
        score += model.latency_score * 1.5

    score += (4 - int(model.cost_tier)) * 0.8
    return score


def select_model(
    task_type: TaskType,
    available_models: dict[str, ModelConfig],
    override_model_id: str | None = None,
) -> str | None:
    if override_model_id and override_model_id in available_models:
        return override_model_id

    req = TASK_REQUIREMENTS[task_type]
    candidates: list[ModelConfig] = []

    for model in available_models.values():
        if not model.enabled:
            continue
        if req.needs_structured_output and not model.supports_structured_output:
            continue
        if req.needs_long_context and not model.supports_long_context:
            continue
        if not _cost_allowed(model.cost_tier, req.max_cost_tier):
            continue
        candidates.append(model)

    if not candidates:
        logger.warning(
            "No eligible models for task=%s, returning None (will use default)",
            task_type,
        )
        return None

    ranked = sorted(candidates, key=lambda m: _score_model(m, task_type), reverse=True)

    chosen = ranked[0]
    logger.info(
        "Router: task=%s → model=%s (score=%.1f, %d candidates)",
        task_type,
        chosen.id,
        _score_model(chosen, task_type),
        len(candidates),
    )
    return chosen.id


def get_fallback_chain(
    task_type: TaskType,
    available_models: dict[str, ModelConfig],
    primary_model_id: str | None = None,
) -> list[str]:
    req = TASK_REQUIREMENTS[task_type]
    candidates: list[ModelConfig] = []

    for model in available_models.values():
        if not model.enabled:
            continue
        if req.needs_structured_output and not model.supports_structured_output:
            continue
        candidates.append(model)

    ranked = sorted(candidates, key=lambda m: _score_model(m, task_type), reverse=True)
    chain = [m.id for m in ranked]

    if primary_model_id and primary_model_id in chain:
        chain.remove(primary_model_id)
        chain.insert(0, primary_model_id)
    elif primary_model_id:
        chain.insert(0, primary_model_id)

    return chain
