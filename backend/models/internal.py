"""Internal Pydantic models for agent-specific structured outputs.

These models are used internally by agents for LLM structured completion responses.
They are not exposed in the public API (backend/schemas/).
"""

from pydantic import BaseModel


class KeywordPlan(BaseModel):
    """LLM response model for keyword generation in planner_agent."""

    keywords: list[str]


class ContributionExtraction(BaseModel):
    """LLM response model for core contribution extraction in extractor_agent."""

    core_contribution: str


class StructuredExtractionResult(BaseModel):
    """LLM response model for detailed paper analysis in extractor_agent."""

    problem: str | None = None
    method: str | None = None
    novelty: str | None = None
    dataset: str | None = None
    baseline: str | None = None
    results: str | None = None
    limitations: str | None = None
    future_work: str | None = None
