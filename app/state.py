import operator
from typing_extensions import Annotated, TypedDict

from app.schemas import PaperMetadata, DraftOutput, PaperSource, ConversationMessage


class AgentState(TypedDict):
    task_id: str
    user_query: str
    search_keywords: list[str]
    candidate_papers: list[PaperMetadata]
    approved_papers: list[PaperMetadata]
    final_draft: DraftOutput | None
    qa_errors: list[str]
    retry_count: int
    logs: Annotated[list[str], operator.add]
    output_language: str
    search_sources: list[PaperSource]
    messages: Annotated[list[ConversationMessage], operator.add]
    is_continuation: bool
