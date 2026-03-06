"""Workflow state, draft output, and processing event schemas."""

from datetime import UTC, datetime
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, Field

from backend.schemas.domain import PaperSource


class MessageRole(StrEnum):
    USER = "user"
    ASSISTANT = "assistant"
    SYSTEM = "system"


class ConversationMessage(BaseModel):
    """A single message in the conversation history."""

    role: MessageRole
    content: str
    timestamp: datetime = Field(default_factory=lambda: datetime.now(UTC))
    metadata: dict[str, Any] | None = None


class ProcessingStage(StrEnum):
    """Workflow processing stages for visualization."""

    PLANNING = "planning"
    SEARCHING = "searching"
    EXTRACTING = "extracting"
    DRAFTING = "drafting"
    QA = "qa"


class PaperProcessingStatus(StrEnum):
    """Status of individual paper processing."""

    PENDING = "pending"
    PROCESSING = "processing"
    COMPLETED = "completed"
    FAILED = "failed"


class SSEEventType(StrEnum):
    """Types of SSE events for frontend visualization."""

    LOG = "log"
    STAGE_CHANGE = "stage_change"
    PAPER_STATUS = "paper_status"
    PROGRESS = "progress"
    DONE = "done"
    ERROR = "error"


class PaperStatusEvent(BaseModel):
    """Event for individual paper processing status updates."""

    paper_id: str
    title: str
    authors: list[str]
    year: int | None = None
    source: PaperSource = PaperSource.SEMANTIC_SCHOLAR
    status: PaperProcessingStatus
    stage: ProcessingStage
    message: str | None = None
    core_contribution: str | None = None


class StageChangeEvent(BaseModel):
    """Event for workflow stage transitions."""

    stage: ProcessingStage
    total_papers: int = 0
    processed_papers: int = 0
    message: str | None = None


class ProgressEvent(BaseModel):
    """Event for overall progress updates."""

    stage: ProcessingStage
    current: int
    total: int
    message: str | None = None


class ReviewSection(BaseModel):
    heading: str
    content: str
    cited_paper_ids: list[str] = []


class DraftOutline(BaseModel):
    title: str
    section_titles: list[str]


class DraftOutput(BaseModel):
    title: str
    sections: list[ReviewSection]


class ErrorCategory(StrEnum):
    """Categories of QA errors for structured reflection."""

    CITATION_OUT_OF_BOUNDS = "citation_out_of_bounds"
    MISSING_CITATION = "missing_citation"
    UNCITED_PAPER = "uncited_paper"
    LOW_ENTAILMENT = "low_entailment"
    STRUCTURAL = "structural"


class ReflectionEntry(BaseModel):
    """A single error analysis with targeted fix strategy."""

    error_category: ErrorCategory
    error_detail: str = Field(description="Specific error description")
    fix_strategy: str = Field(description="Concrete fix instruction for the writer")
    fixable_by_writer: bool = Field(description="True if writer can fix; False if retriever needed")


class Reflection(BaseModel):
    """Structured reflection on QA errors with routing decision."""

    entries: list[ReflectionEntry] = Field(description="Analyzed errors with fix strategies")
    should_retry: bool = Field(description="Whether a retry is warranted")
    retry_target: str = Field(
        default="writer_agent",
        description="Target node: 'writer_agent' or 'retriever_agent'",
    )
    summary: str = Field(description="Brief reflection summary for logging")
