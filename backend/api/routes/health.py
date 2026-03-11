"""Health check endpoints."""

import logging
from typing import Any

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse

from backend.core.lifecycle import check_dependency_health, is_shutting_down
from backend.utils.llm_client import get_client

logger = logging.getLogger(__name__)

router = APIRouter(tags=["health"])


@router.get("/healthz")
async def healthz():
    """Liveness probe - returns 200 if process is alive."""
    return JSONResponse(content={"status": "ok"})


@router.get("/readyz")
async def readyz(request: Request):
    """Readiness probe - checks if service can handle requests.

    Only checks core dependencies required for all requests.
    Optional features (vector pipeline) are not checked here.
    """
    app = request.app
    checks: dict[str, bool] = {
        "workflow": hasattr(app.state, "graph") and app.state.graph is not None,
        "checkpoint_db": False,
        "shutdown": is_shutting_down.value,
    }
    errors: dict[str, str] = {}

    if not checks["workflow"]:
        errors["workflow"] = "workflow_not_initialized"

    if checks["shutdown"]:
        errors["shutdown"] = "service_shutting_down"

    if checks["workflow"]:
        try:
            checkpointer = app.state.graph.checkpointer
            async for _ in checkpointer.alist(None, limit=1):
                checks["checkpoint_db"] = True
                break
            if not checks["checkpoint_db"]:
                checks["checkpoint_db"] = True
        except Exception as e:
            logger.warning("Checkpoint DB health check failed: %s", e)
            errors["checkpoint_db"] = str(e)

    is_ready = checks["workflow"] and checks["checkpoint_db"] and not checks["shutdown"]
    payload: dict[str, Any] = {
        "status": "ready" if is_ready else "not ready",
        "checks": checks,
    }
    if errors:
        payload["errors"] = errors

    return JSONResponse(content=payload, status_code=200 if is_ready else 503)


@router.get("/startupz")
async def startupz(request: Request):
    """Startup probe - validates workflow initialization and LLM connectivity.

    Runs once during pod startup. Checks critical dependencies that must be
    available before accepting traffic.
    """
    app = request.app
    checks: dict[str, bool] = {
        "workflow": hasattr(app.state, "graph") and app.state.graph is not None,
        "llm_connectivity": False,
    }
    errors: dict[str, str] = {}

    if not checks["workflow"]:
        errors["workflow"] = "workflow_not_initialized"

    if checks["workflow"]:
        llm_check_result, llm_error = await check_dependency_health(
            "llm_api", lambda: get_client().models.list(), timeout_seconds=2.0
        )
        checks["llm_connectivity"] = llm_check_result
        if not llm_check_result and llm_error:
            errors["llm_connectivity"] = llm_error

    is_started = checks["workflow"] and checks["llm_connectivity"]
    payload: dict[str, Any] = {
        "status": "started" if is_started else "not started",
        "workflow_initialized": checks["workflow"],
        "llm_connectivity": checks["llm_connectivity"],
    }
    if errors:
        payload["errors"] = errors

    return JSONResponse(content=payload, status_code=200 if is_started else 503)


__all__ = ["router"]
