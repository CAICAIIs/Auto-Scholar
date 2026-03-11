"""Health check endpoints."""

from typing import Any

from fastapi import APIRouter
from fastapi.responses import JSONResponse

router = APIRouter(tags=["health"])

# Will be populated with health check endpoints
# Endpoints: /healthz, /readyz, /startupz

__all__ = ["router"]
