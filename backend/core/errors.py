"""Typed exception hierarchy for Auto-Scholar domain errors.

Use these exceptions to represent structured, machine-readable failures
across workflow, validation, search, extraction, and LLM interactions.
"""

from typing import Any


class AutoScholarError(Exception):
    """Base class for all structured application errors.

    Raise this type (or subclasses) when you need consistent API error
    responses with optional debugging context.
    """

    def __init__(self, message: str, details: dict[str, Any] | None = None) -> None:
        self.message = message
        self.details = details
        super().__init__(message)

    def __str__(self) -> str:
        if self.details:
            return f"{self.message} | details={self.details}"
        return self.message


class ValidationError(AutoScholarError):
    """Raised when user input or request payload fails validation."""


class WorkflowError(AutoScholarError):
    """Raised when workflow orchestration or state transitions fail."""


class ExtractionError(AutoScholarError):
    """Raised when extracting structured content from papers fails."""


class SearchError(AutoScholarError):
    """Raised when paper discovery/search operations fail."""


class LLMError(AutoScholarError):
    """Raised when upstream LLM providers return errors or invalid outputs."""


class TimeoutError(AutoScholarError):
    """Raised when an operation exceeds configured timeout limits."""


class ConfigurationError(AutoScholarError):
    """Raised when application or model configuration is invalid."""
