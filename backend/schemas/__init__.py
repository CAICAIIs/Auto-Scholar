"""Schema package with backward-compatible re-exports.

This package organizes Pydantic models by concern:
- api.py: API request/response models and configuration
- workflow.py: Workflow state, draft output, and processing events
- domain.py: Domain entities (papers, sources, structured data)

All models are re-exported from this __init__.py for backward compatibility.
"""

# Domain models
# API models
from backend.schemas.api import (
    ApproveRequest,
    ApproveResponse,
    CitationStyle,
    ContinueRequest,
    ContinueResponse,
    CostTier,
    ModelConfig,
    ModelProvider,
    SessionDetail,
    SessionSummary,
    StartRequest,
    StartResponse,
)
from backend.schemas.domain import (
    BatchClaimList,
    Claim,
    ClaimVerificationResult,
    ClaimVerificationSummary,
    EntailmentLabel,
    MethodComparisonEntry,
    PaperMetadata,
    PaperSource,
    ResearchPlan,
    SectionClaim,
    StructuredContribution,
    SubQuestion,
)

# Workflow models
from backend.schemas.workflow import (
    ConversationMessage,
    DraftOutline,
    DraftOutput,
    ErrorCategory,
    MessageRole,
    PaperProcessingStatus,
    PaperStatusEvent,
    ProcessingStage,
    ProgressEvent,
    Reflection,
    ReflectionEntry,
    ReviewSection,
    SSEEventType,
    StageChangeEvent,
)

__all__ = [
    # Domain
    "BatchClaimList",
    "Claim",
    "ClaimVerificationResult",
    "ClaimVerificationSummary",
    "EntailmentLabel",
    "MethodComparisonEntry",
    "PaperMetadata",
    "PaperSource",
    "ResearchPlan",
    "SectionClaim",
    "StructuredContribution",
    "SubQuestion",
    # Workflow
    "ConversationMessage",
    "DraftOutline",
    "DraftOutput",
    "ErrorCategory",
    "MessageRole",
    "PaperProcessingStatus",
    "PaperStatusEvent",
    "ProcessingStage",
    "ProgressEvent",
    "Reflection",
    "ReflectionEntry",
    "ReviewSection",
    "SSEEventType",
    "StageChangeEvent",
    # API
    "ApproveRequest",
    "ApproveResponse",
    "CitationStyle",
    "ContinueRequest",
    "ContinueResponse",
    "CostTier",
    "ModelConfig",
    "ModelProvider",
    "SessionDetail",
    "SessionSummary",
    "StartRequest",
    "StartResponse",
]
