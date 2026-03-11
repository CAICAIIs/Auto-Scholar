"""Model management endpoints."""

from fastapi import APIRouter

router = APIRouter(prefix="/api", tags=["models"])

# Will be populated with model endpoints
# Endpoints: /models, /models/health

__all__ = ["router"]
