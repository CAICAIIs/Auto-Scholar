"""Pydantic models for the 7-dimension evaluation framework."""

from datetime import UTC, datetime
from typing import Any

from pydantic import BaseModel, Field, computed_field


class CitationPrecisionResult(BaseModel):
    """Citation precision: % of citations where 1 <= N <= num_approved_papers."""

    total_citations: int = Field(ge=0)
    valid_citations: int = Field(ge=0)
    invalid_indices: list[int] = Field(default_factory=list)

    @computed_field  # type: ignore[prop-decorator]
    @property
    def precision(self) -> float:
        if self.total_citations == 0:
            return 1.0
        return self.valid_citations / self.total_citations


class CitationRecallResult(BaseModel):
    """Citation recall: % of approved papers that are actually cited."""

    total_approved: int = Field(ge=0)
    cited_count: int = Field(ge=0)
    uncited_indices: list[int] = Field(default_factory=list)

    @computed_field  # type: ignore[prop-decorator]
    @property
    def recall(self) -> float:
        if self.total_approved == 0:
            return 1.0
        return self.cited_count / self.total_approved


class SectionCompletenessResult(BaseModel):
    """Section completeness: whether all required sections exist."""

    required_sections: list[str]
    present_sections: list[str]
    missing_sections: list[str] = Field(default_factory=list)
    extra_sections: list[str] = Field(default_factory=list)

    @computed_field  # type: ignore[prop-decorator]
    @property
    def completeness_score(self) -> float:
        if len(self.required_sections) == 0:
            return 1.0
        present_count = len(self.required_sections) - len(self.missing_sections)
        return present_count / len(self.required_sections)


class AcademicStyleResult(BaseModel):
    """Academic style: hedging ratio, passive voice ratio, citation density."""

    total_sentences: int = Field(ge=0)
    hedging_count: int = Field(ge=0)
    passive_count: int = Field(ge=0)
    total_words: int = Field(ge=0)
    citation_count: int = Field(ge=0)

    @computed_field  # type: ignore[prop-decorator]
    @property
    def hedging_ratio(self) -> float:
        if self.total_sentences == 0:
            return 0.0
        return self.hedging_count / self.total_sentences

    @computed_field  # type: ignore[prop-decorator]
    @property
    def passive_ratio(self) -> float:
        if self.total_sentences == 0:
            return 0.0
        return self.passive_count / self.total_sentences

    @computed_field  # type: ignore[prop-decorator]
    @property
    def citation_density(self) -> float:
        """Citations per 100 words."""
        if self.total_words == 0:
            return 0.0
        return (self.citation_count / self.total_words) * 100


class TaskCostBreakdown(BaseModel):
    task_type: str
    prompt_tokens: int = Field(ge=0, default=0)
    completion_tokens: int = Field(ge=0, default=0)
    llm_calls: int = Field(ge=0, default=0)
    cost_usd: float = Field(ge=0, default=0.0)

    @computed_field  # type: ignore[prop-decorator]
    @property
    def total_tokens(self) -> int:
        return self.prompt_tokens + self.completion_tokens


class CostEfficiencyResult(BaseModel):
    prompt_tokens: int = Field(ge=0)
    completion_tokens: int = Field(ge=0)
    total_llm_calls: int = Field(ge=0)
    total_search_calls: int = Field(ge=0)
    total_latency_ms: float = Field(ge=0)
    node_timings: dict[str, float] = Field(default_factory=dict)
    total_cost_usd: float = Field(ge=0, default=0.0)
    task_breakdown: list[TaskCostBreakdown] = Field(default_factory=list)

    @computed_field  # type: ignore[prop-decorator]
    @property
    def total_tokens(self) -> int:
        return self.prompt_tokens + self.completion_tokens

    @computed_field  # type: ignore[prop-decorator]
    @property
    def avg_tokens_per_call(self) -> float:
        if self.total_llm_calls == 0:
            return 0.0
        return self.total_tokens / self.total_llm_calls


class HumanRating(BaseModel):
    """Human preference rating (1-5 Likert scale) for A/B testing."""

    thread_id: str
    rater_id: str
    timestamp: datetime = Field(default_factory=lambda: datetime.now(UTC))

    overall_quality: int = Field(ge=1, le=5)
    factual_accuracy: int = Field(ge=1, le=5)
    coherence: int = Field(ge=1, le=5)
    completeness: int = Field(ge=1, le=5)
    writing_quality: int = Field(ge=1, le=5)

    comments: str = Field(default="")

    @computed_field  # type: ignore[prop-decorator]
    @property
    def average_rating(self) -> float:
        ratings = [
            self.overall_quality,
            self.factual_accuracy,
            self.coherence,
            self.completeness,
            self.writing_quality,
        ]
        return sum(ratings) / len(ratings)


class HumanRatingSummary(BaseModel):
    """Aggregated human ratings for a thread."""

    thread_id: str
    rating_count: int = Field(ge=0)
    avg_overall: float = Field(ge=0, le=5)
    avg_accuracy: float = Field(ge=0, le=5)
    avg_coherence: float = Field(ge=0, le=5)
    avg_completeness: float = Field(ge=0, le=5)
    avg_writing: float = Field(ge=0, le=5)


class EvaluationResult(BaseModel):
    """Unified evaluation result aggregating all 7 dimensions."""

    thread_id: str
    timestamp: datetime = Field(default_factory=lambda: datetime.now(UTC))

    citation_precision: CitationPrecisionResult
    citation_recall: CitationRecallResult
    claim_support_rate: float = Field(ge=0, le=1)
    section_completeness: SectionCompletenessResult
    academic_style: AcademicStyleResult
    cost_efficiency: CostEfficiencyResult

    human_ratings: HumanRatingSummary | None = None

    language: str = Field(default="en")
    paper_count: int = Field(ge=0)
    metadata: dict[str, Any] = Field(default_factory=dict)

    @computed_field  # type: ignore[prop-decorator]
    @property
    def automated_score(self) -> float:
        """Weighted average: precision 20%, recall 15%, claim 25%, section 20%, style 20%."""
        hedging = self.academic_style.hedging_ratio
        if 0.05 <= hedging <= 0.20:
            hedging_score = 1.0
        elif hedging < 0.05:
            hedging_score = hedging / 0.05
        else:
            hedging_score = max(0, 1 - (hedging - 0.20) / 0.20)

        return (
            0.20 * self.citation_precision.precision
            + 0.15 * self.citation_recall.recall
            + 0.25 * self.claim_support_rate
            + 0.20 * self.section_completeness.completeness_score
            + 0.20 * hedging_score
        )
