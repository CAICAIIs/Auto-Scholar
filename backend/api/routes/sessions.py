"""Session management endpoints."""

from fastapi import APIRouter

router = APIRouter(prefix="/api/research", tags=["sessions"])

# Will be populated with session endpoints
# Endpoints: /sessions, /sessions/{thread_id}

__all__ = ["router"]
