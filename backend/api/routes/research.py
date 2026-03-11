"""Research workflow endpoints."""

from fastapi import APIRouter

router = APIRouter(prefix="/api/research", tags=["research"])

# Will be populated with research workflow endpoints
# Endpoints: /start, /approve, /continue, /status/{thread_id}, /stream/{thread_id}

__all__ = ["router"]
