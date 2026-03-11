"""Model management endpoints."""

from fastapi import APIRouter
from pydantic import BaseModel

from backend.llm.health import get_model_health
from backend.schemas import ModelConfig
from backend.utils.llm_client import list_models

router = APIRouter(prefix="/api", tags=["models"])


@router.get("/models", response_model=list[ModelConfig])
async def get_available_models():
    return list_models()


class ModelHealthResponse(BaseModel):
    model_id: str
    provider: str
    state: str
    recent_failures: int
    last_failure_at: float | None = None


@router.get("/models/health", response_model=list[ModelHealthResponse])
async def get_model_health_status():
    return [
        ModelHealthResponse(
            model_id=health.model_id,
            provider=health.provider,
            state=health.state.value,
            recent_failures=health.recent_failures,
            last_failure_at=health.last_failure_at,
        )
        for health in (get_model_health(model) for model in list_models())
    ]


__all__ = ["router", "ModelHealthResponse"]
