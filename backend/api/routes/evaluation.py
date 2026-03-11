"""Evaluation and ratings endpoints."""

from fastapi import APIRouter

router = APIRouter(prefix="/api", tags=["evaluation"])

# Will be populated with evaluation endpoints
# Endpoints: /research/evaluate/{thread_id}, /ratings, /ratings/{thread_id}

__all__ = ["router"]
