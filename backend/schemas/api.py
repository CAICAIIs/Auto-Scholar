"""API request/response models and configuration schemas."""

from enum import IntEnum, StrEnum
from typing import TYPE_CHECKING

from pydantic import BaseModel, Field

from backend.schemas.domain import PaperMetadata, PaperSource
from backend.schemas.workflow import ConversationMessage, DraftOutput

if TYPE_CHECKING:
    pass


class ModelProvider(StrEnum):
    """Supported LLM providers."""

    OPENAI = "openai"
    DEEPSEEK = "deepseek"
    OLLAMA = "ollama"
    CUSTOM = "custom"


class CostTier(IntEnum):
    LOW = 1
    MEDIUM = 2
    HIGH = 3


class ModelConfig(BaseModel):
    """Configuration for a single LLM model."""

    id: str = Field(description="Canonical model ID, e.g. 'openai:gpt-4o'")
    provider: ModelProvider
    model_name: str = Field(description="Provider-specific model name, e.g. 'gpt-4o'")
    display_name: str = Field(description="Human-readable name for UI")
    api_base: str = Field(description="API base URL for this provider")
    api_key_env: str = Field(
        default="LLM_API_KEY",
        description="Environment variable name for the API key",
    )
    supports_json_mode: bool = Field(
        default=True,
        description="Whether the model supports response_format={'type': 'json_object'}",
    )
    supports_structured_output: bool = Field(
        default=True,
        description="Whether the model reliably produces structured JSON",
    )
    max_output_tokens: int = Field(default=8192, description="Maximum output tokens")
    is_local: bool = Field(default=False, description="Whether this is a local model (e.g. Ollama)")
    enabled: bool = Field(default=True, description="Whether this model is available for selection")

    max_context_tokens: int = Field(default=128_000, description="Maximum context window size")
    supports_long_context: bool = Field(default=True, description="Context window >= 32K tokens")
    cost_tier: CostTier = Field(default=CostTier.HIGH, description="Cost classification")
    reasoning_score: int = Field(default=7, ge=1, le=10, description="Reasoning ability (1-10)")
    creativity_score: int = Field(
        default=7, ge=1, le=10, description="Creative writing ability (1-10)"
    )
    latency_score: int = Field(default=5, ge=1, le=10, description="Speed (1=slow, 10=fast)")


class CitationStyle(StrEnum):
    APA = "apa"
    MLA = "mla"
    IEEE = "ieee"
    GB_T7714 = "gb-t7714"


class StartRequest(BaseModel):
    query: str
    language: str = "en"
    sources: list["PaperSource"] = Field(
        default_factory=lambda: [
            PaperSource.SEMANTIC_SCHOLAR,
            PaperSource.ARXIV,
            PaperSource.PUBMED,
        ]
    )
    model_id: str | None = None


class StartResponse(BaseModel):
    thread_id: str
    candidate_papers: list["PaperMetadata"]
    logs: list[str]


class ApproveRequest(BaseModel):
    thread_id: str
    paper_ids: list[str]


class ApproveResponse(BaseModel):
    thread_id: str
    final_draft: "DraftOutput | None" = None
    approved_count: int
    logs: list[str] = []


class ContinueRequest(BaseModel):
    thread_id: str
    message: str
    model_id: str | None = None


class ContinueResponse(BaseModel):
    thread_id: str
    message: "ConversationMessage | None" = None
    final_draft: "DraftOutput | None" = None
    candidate_papers: list["PaperMetadata"] = []
    logs: list[str] = []


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
    candidate_papers: list["PaperMetadata"]
    approved_papers: list["PaperMetadata"]
    final_draft: "DraftOutput | None"
    logs: list[str]
    messages: list["ConversationMessage"] = []


StartRequest.model_rebuild()
StartResponse.model_rebuild()
ApproveResponse.model_rebuild()
ContinueResponse.model_rebuild()
SessionDetail.model_rebuild()
