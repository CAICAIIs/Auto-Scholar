from __future__ import annotations

import time
from dataclasses import dataclass
from enum import StrEnum

from backend.constants import MODEL_SKIP_THRESHOLD, MODEL_SKIP_WINDOW_SECONDS
from backend.schemas import ModelConfig


class CircuitState(StrEnum):
    CLOSED = "closed"
    OPEN = "open"


@dataclass(frozen=True)
class HealthStatus:
    model_id: str
    provider: str
    state: CircuitState
    recent_failures: int
    last_failure_at: float | None


_failures: dict[str, list[float]] = {}


def _prune_failures(model_id: str, now: float | None = None) -> list[float]:
    current_time = now if now is not None else time.time()
    timestamps = _failures.get(model_id, [])
    recent = [ts for ts in timestamps if current_time - ts < MODEL_SKIP_WINDOW_SECONDS]
    _failures[model_id] = recent
    return recent


def should_skip_model(model_id: str) -> bool:
    return len(_prune_failures(model_id)) >= MODEL_SKIP_THRESHOLD


def record_model_failure(model_id: str) -> None:
    recent = _prune_failures(model_id)
    recent.append(time.time())
    _failures[model_id] = recent


def record_model_success(model_id: str) -> None:
    _failures.pop(model_id, None)


def get_model_health(model: ModelConfig) -> HealthStatus:
    recent = _prune_failures(model.id)
    return HealthStatus(
        model_id=model.id,
        provider=model.provider.value,
        state=CircuitState.OPEN if len(recent) >= MODEL_SKIP_THRESHOLD else CircuitState.CLOSED,
        recent_failures=len(recent),
        last_failure_at=recent[-1] if recent else None,
    )


def reset_model_health() -> None:
    _failures.clear()
