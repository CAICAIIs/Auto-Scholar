from datetime import datetime, timezone
from enum import Enum
from typing import Any

from pydantic import BaseModel, Field


class PaperSource(str, Enum):
    SEMANTIC_SCHOLAR = "semantic_scholar"
    ARXIV = "arxiv"
    PUBMED = "pubmed"


class MessageRole(str, Enum):
    USER = "user"
    ASSISTANT = "assistant"
    SYSTEM = "system"


class ConversationMessage(BaseModel):
    """A single message in the conversation history."""
    role: MessageRole
    content: str
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    metadata: dict[str, Any] | None = None


class CitationStyle(str, Enum):
    APA = "apa"
    MLA = "mla"
    IEEE = "ieee"
    GB_T7714 = "gb-t7714"


class ProcessingStage(str, Enum):
    """Workflow processing stages for visualization."""
    PLANNING = "planning"
    SEARCHING = "searching"
    EXTRACTING = "extracting"
    DRAFTING = "drafting"
    QA = "qa"


class PaperProcessingStatus(str, Enum):
    """Status of individual paper processing."""
    PENDING = "pending"
    PROCESSING = "processing"
    COMPLETED = "completed"
    FAILED = "failed"


class SSEEventType(str, Enum):
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


class PaperMetadata(BaseModel):
    paper_id: str
    title: str
    authors: list[str]
    abstract: str
    url: str
    year: int | None = None
    doi: str | None = None
    pdf_url: str | None = None
    is_approved: bool = False
    core_contribution: str | None = None
    source: PaperSource = PaperSource.SEMANTIC_SCHOLAR


class ReviewSection(BaseModel):
    heading: str
    content: str  # Must contain {cite:N} style inline citations
    cited_paper_ids: list[str] = []  # Populated by post-processing, not LLM


class DraftOutput(BaseModel):
    title: str
    sections: list[ReviewSection]


class StartRequest(BaseModel):
    query: str
    language: str = "en"
    sources: list[PaperSource] = [PaperSource.SEMANTIC_SCHOLAR]


class StartResponse(BaseModel):
    thread_id: str
    candidate_papers: list[PaperMetadata]
    logs: list[str]


class ApproveRequest(BaseModel):
    thread_id: str
    paper_ids: list[str]


class ApproveResponse(BaseModel):
    thread_id: str
    final_draft: DraftOutput | None
    approved_count: int
    logs: list[str]


class ContinueRequest(BaseModel):
    thread_id: str
    message: str


class ContinueResponse(BaseModel):
    thread_id: str
    message: ConversationMessage
    final_draft: DraftOutput | None
    candidate_papers: list[PaperMetadata]
    logs: list[str]


class SessionSummary(BaseModel):
    thread_id: str
    user_query: str
    status: str
    paper_count: int
    has_draft: bool
    created_at: str | None = None


class SessionDetail(BaseModel):
    thread_id: str
    user_query: str
    status: str
    candidate_papers: list[PaperMetadata]
    approved_papers: list[PaperMetadata]
    final_draft: DraftOutput | None
    logs: list[str]
    messages: list[ConversationMessage] = []
