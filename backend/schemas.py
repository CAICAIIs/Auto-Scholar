from datetime import UTC, datetime
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, Field


class PaperSource(StrEnum):
    SEMANTIC_SCHOLAR = "semantic_scholar"
    ARXIV = "arxiv"
    PUBMED = "pubmed"


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


class CitationStyle(StrEnum):
    APA = "apa"
    MLA = "mla"
    IEEE = "ieee"
    GB_T7714 = "gb-t7714"


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


class StructuredContribution(BaseModel):
    """8-dimension structured extraction from paper abstract.

    All fields are optional since not all papers contain all information.
    For example, theoretical papers may not have datasets or baselines.
    """

    problem: str | None = None
    """Research problem being addressed."""

    method: str | None = None
    """Methodology or approach used."""

    novelty: str | None = None
    """Key innovations or contributions."""

    dataset: str | None = None
    """Datasets used for experiments (null for theoretical papers)."""

    baseline: str | None = None
    """Baseline methods compared against (null if no comparison)."""

    results: str | None = None
    """Key experimental results or findings."""

    limitations: str | None = None
    """Limitations acknowledged by authors (null if not mentioned)."""

    future_work: str | None = None
    """Future directions suggested (null if not mentioned)."""


class MethodComparisonEntry(BaseModel):
    """A single row in the method comparison table."""

    paper_index: int
    """1-based index of the paper in the review."""

    title: str
    """Paper title (truncated if too long)."""

    method: str | None = None
    """Method/approach summary."""

    dataset: str | None = None
    """Dataset used."""

    baseline: str | None = None
    """Baselines compared."""

    results: str | None = None
    """Key results."""


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
    structured_contribution: StructuredContribution | None = None
    source: PaperSource = PaperSource.SEMANTIC_SCHOLAR


class EntailmentLabel(StrEnum):
    """Three-way entailment labels for claim verification."""

    ENTAILS = "entails"  # Citation supports the claim
    INSUFFICIENT = "insufficient"  # Citation doesn't provide enough evidence
    CONTRADICTS = "contradicts"  # Citation contradicts the claim


class SectionClaim(BaseModel):
    """Claims extracted from a single section in batch extraction."""

    section_index: int
    claims: list[str]


class BatchClaimList(BaseModel):
    """Claims extracted from multiple sections in batch."""

    sections_claims: list[SectionClaim]


class Claim(BaseModel):
    """An atomic claim extracted from the review text."""

    claim_id: str
    text: str  # The claim text
    section_index: int  # Which section this claim belongs to
    citation_indices: list[int] = []  # Paper indices cited (1-based)


class ClaimVerificationResult(BaseModel):
    """Result of verifying a single claim against its cited papers."""

    claim_id: str
    claim_text: str
    citation_index: int  # The paper index being verified (1-based)
    paper_title: str  # Title of the cited paper
    label: EntailmentLabel
    confidence: float = Field(ge=0.0, le=1.0)
    evidence_snippet: str = ""  # Relevant snippet from paper that supports/contradicts
    rationale: str = ""  # Brief explanation of the verdict


class ClaimVerificationSummary(BaseModel):
    """Summary of all claim verifications for a draft."""

    total_claims: int
    total_verifications: int
    entails_count: int
    insufficient_count: int
    contradicts_count: int
    failed_verifications: list[ClaimVerificationResult] = []


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


class SubQuestion(BaseModel):
    """A sub-question decomposed from the user's research query."""

    question: str = Field(description="Sub-question text")
    keywords: list[str] = Field(
        description="Search keywords for this sub-question",
        min_length=2,
        max_length=5,
    )
    preferred_source: PaperSource = Field(
        default=PaperSource.SEMANTIC_SCHOLAR,
        description="Recommended data source for this sub-question",
    )
    estimated_papers: int = Field(
        default=5,
        description="Estimated number of papers needed",
        ge=3,
        le=15,
    )
    priority: int = Field(
        default=1,
        description="Priority level (1 = highest)",
        ge=1,
        le=5,
    )


class ResearchPlan(BaseModel):
    """Structured research plan with CoT reasoning and sub-question decomposition."""

    reasoning: str = Field(description="Chain-of-thought reasoning for the decomposition")
    sub_questions: list[SubQuestion] = Field(description="Decomposed sub-questions")
    total_estimated_papers: int = Field(
        default=0,
        description="Total estimated papers across all sub-questions",
    )


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


class StartRequest(BaseModel):
    query: str
    language: str = "en"
    sources: list[PaperSource] = [
        PaperSource.SEMANTIC_SCHOLAR,
        PaperSource.ARXIV,
        PaperSource.PUBMED,
    ]


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
