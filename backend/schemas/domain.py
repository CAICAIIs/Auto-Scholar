"""Domain entities for papers, sources, and structured data."""

from datetime import datetime
from enum import StrEnum

from pydantic import BaseModel, Field


class PaperSource(StrEnum):
    SEMANTIC_SCHOLAR = "semantic_scholar"
    ARXIV = "arxiv"
    PUBMED = "pubmed"


class StructuredContribution(BaseModel):
    """8-dimension structured extraction from paper abstract.

    All fields are optional since not all papers contain all information.
    For example, theoretical papers may not have datasets or baselines.
    """

    problem: str | None = None
    method: str | None = None
    novelty: str | None = None
    dataset: str | None = None
    baseline: str | None = None
    results: str | None = None
    limitations: str | None = None
    future_work: str | None = None


class PaperMetadata(BaseModel):
    paper_id: str
    title: str
    authors: list[str]
    abstract: str
    url: str
    year: int | None = None
    doi: str | None = None
    pdf_url: str | None = None
    pdf_object_key: str | None = Field(
        default=None,
        description="MinIO object key for downloaded PDF",
    )
    pdf_content_hash: str | None = Field(
        default=None,
        description="SHA256 hash of PDF URL for cache deduplication",
    )
    pdf_downloaded_at: datetime | None = Field(
        default=None,
        description="Timestamp when PDF was successfully downloaded to MinIO",
    )
    pdf_size_bytes: int | None = Field(
        default=None,
        description="Size of downloaded PDF file in bytes",
    )
    is_approved: bool = False
    core_contribution: str | None = None
    structured_contribution: StructuredContribution | None = None
    source: PaperSource = PaperSource.SEMANTIC_SCHOLAR


class MethodComparisonEntry(BaseModel):
    """A single row in the method comparison table."""

    paper_index: int
    title: str
    method: str | None = None
    dataset: str | None = None
    baseline: str | None = None
    results: str | None = None


class EntailmentLabel(StrEnum):
    """Three-way entailment labels for claim verification."""

    ENTAILS = "entails"
    INSUFFICIENT = "insufficient"
    CONTRADICTS = "contradicts"


class Claim(BaseModel):
    """An atomic claim extracted from the review text."""

    claim_id: str
    text: str
    section_index: int
    citation_indices: list[int] = []


class SectionClaim(BaseModel):
    """Claims extracted from a single section in batch extraction."""

    section_index: int
    claims: list[str]


class BatchClaimList(BaseModel):
    """Claims extracted from multiple sections in batch."""

    sections_claims: list[SectionClaim]


class ClaimVerificationResult(BaseModel):
    """Result of verifying a single claim against its cited papers."""

    claim_id: str
    claim_text: str
    citation_index: int
    paper_title: str
    label: EntailmentLabel
    confidence: float = Field(ge=0.0, le=1.0)
    evidence_snippet: str = ""
    rationale: str = ""


class ClaimVerificationSummary(BaseModel):
    """Summary of all claim verifications for a draft."""

    total_claims: int
    total_verifications: int
    entails_count: int
    insufficient_count: int
    contradicts_count: int
    failed_verifications: list[ClaimVerificationResult] = []


class SubQuestion(BaseModel):
    """A sub-question decomposed from the user's research query."""

    question: str = Field(description="Sub-question text")
    keywords: list[str] = Field(
        description="Search keywords for this n",
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
