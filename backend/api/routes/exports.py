"""Export and charts endpoints."""

from fastapi import APIRouter

router = APIRouter(prefix="/api/research", tags=["export"])

# Will be populated with export endpoints
# Endpoints: /export, /charts

__all__ = ["router"]
