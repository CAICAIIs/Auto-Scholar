"""DEPRECATED: Compatibility shell for backward compatibility.

This file is kept for backward compatibility only. All models have been
moved to the backend.schemas package (schemas/api.py, schemas/workflow.py,
schemas/domain.py).

New code should import from backend.schemas package:
    from backend.schemas import PaperMetadata, StartRequest, DraftOutput

This file will be removed in a future version.
"""

from backend.schemas import *  # noqa: F401, F403, F405

__all__ = [  # noqa: F405
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
