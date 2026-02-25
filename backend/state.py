import operator
from typing import Annotated

from typing_extensions import TypedDict

from backend.schemas import (
    ClaimVerificationSummary,
    ConversationMessage,
    DraftOutline,
    DraftOutput,
    PaperMetadata,
    PaperSource,
    Reflection,
    ResearchPlan,
)


class AgentState(TypedDict):
    task_id: str
    user_query: str
    search_keywords: list[str]
    candidate_papers: list[PaperMetadata]
    approved_papers: list[PaperMetadata]
    selected_papers: list[PaperMetadata]
    final_draft: DraftOutput | None
    qa_errors: list[str]
    retry_count: int
    logs: Annotated[list[str], operator.add]
    output_language: str
    search_sources: list[PaperSource]
    messages: Annotated[list[ConversationMessage], operator.add]
    is_continuation: bool
    current_agent: str
    agent_handoffs: Annotated[list[str], operator.add]
    draft_outline: DraftOutline | None
    claim_verification: ClaimVerificationSummary | None
    research_plan: ResearchPlan | None
    reflection: Reflection | None
    model_id: str | None
