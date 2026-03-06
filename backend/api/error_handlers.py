"""FastAPI exception handlers for structured error responses.

Translates domain exceptions into consistent JSON error payloads with
appropriate HTTP status codes.
"""

from typing import Any

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from backend.core.errors import (
    AutoScholarError,
    ConfigurationError,
    ExtractionError,
    LLMError,
    SearchError,
    TimeoutError,
    ValidationError,
    WorkflowError,
)


def _error_response(
    error_type: str, message: str, status_code: int, details: dict[str, Any] | None = None
) -> JSONResponse:
    """Create standardized JSON error response."""
    content = {"error": error_type, "message": message}
    if details:
        content["details"] = details
    return JSONResponse(status_code=status_code, content=content)


async def handle_validation_error(request: Request, exc: ValidationError) -> JSONResponse:
    """Handle validation errors with 400 Bad Request."""
    return _error_response("validation_error", exc.message, 400, exc.details)


async def handle_configuration_error(request: Request, exc: ConfigurationError) -> JSONResponse:
    """Handle configuration errors with 500 Internal Server Error."""
    return _error_response("configuration_error", exc.message, 500, exc.details)


async def handle_timeout_error(request: Request, exc: TimeoutError) -> JSONResponse:
    """Handle timeout errors with 504 Gateway Timeout."""
    return _error_response("timeout_error", exc.message, 504, exc.details)


async def handle_llm_error(request: Request, exc: LLMError) -> JSONResponse:
    """Handle LLM provider errors with 502 Bad Gateway."""
    return _error_response("llm_error", exc.message, 502, exc.details)


async def handle_workflow_error(request: Request, exc: WorkflowError) -> JSONResponse:
    """Handle workflow errors with 500 Internal Server Error."""
    return _error_response("workflow_error", exc.message, 500, exc.details)


async def handle_extraction_error(request: Request, exc: ExtractionError) -> JSONResponse:
    """Handle extraction errors with 500 Internal Server Error."""
    return _error_response("extraction_error", exc.message, 500, exc.details)


async def handle_search_error(request: Request, exc: SearchError) -> JSONResponse:
    """Handle search errors with 500 Internal Server Error."""
    return _error_response("search_error", exc.message, 500, exc.details)


async def handle_auto_scholar_error(request: Request, exc: AutoScholarError) -> JSONResponse:
    """Handle generic AutoScholarError with 500 Internal Server Error."""
    return _error_response("auto_scholar_error", exc.message, 500, exc.details)


def register_error_handlers(app: FastAPI) -> None:
    """Register all exception handlers with the FastAPI app.

    Call this during app initialization to enable structured error responses.
    """
    app.add_exception_handler(ValidationError, handle_validation_error)
    app.add_exception_handler(ConfigurationError, handle_configuration_error)
    app.add_exception_handler(TimeoutError, handle_timeout_error)
    app.add_exception_handler(LLMError, handle_llm_error)
    app.add_exception_handler(WorkflowError, handle_workflow_error)
    app.add_exception_handler(ExtractionError, handle_extraction_error)
    app.add_exception_handler(SearchError, handle_search_error)
    app.add_exception_handler(AutoScholarError, handle_auto_scholar_error)
