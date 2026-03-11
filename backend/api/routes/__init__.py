"""API routes package.

Domain-specific route handlers organized by feature.
"""

from backend.api.routes.evaluation import router as evaluation_router
from backend.api.routes.exports import router as exports_router
from backend.api.routes.health import router as health_router
from backend.api.routes.models import router as models_router
from backend.api.routes.research import router as research_router
from backend.api.routes.sessions import router as sessions_router

__all__ = [
    "evaluation_router",
    "exports_router",
    "health_router",
    "models_router",
    "research_router",
    "sessions_router",
]
