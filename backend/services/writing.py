import logging

from openai.types.chat import ChatCompletionMessageParam

from backend.llm.execution import build_execution_plan, execute_structured
from backend.llm.registry import get_model_registry
from backend.llm.runtime import build_runtime_selection
from backend.constants import get_section_max_tokens
from backend.prompts import (
    DRAFT_USER_PROMPT,
    OUTLINE_GENERATION_SYSTEM,
    SECTION_GENERATION_SYSTEM,
)
from backend.schemas import DraftOutline, ReviewSection
from backend.utils.llm_client import (
    _build_schema_prompt,
    _call_llm,
    _call_llm_streaming,
    resolve_model,
    token_callback_var,
)

logger = logging.getLogger(__name__)


async def execute_task_completion(
    *,
    messages: list[ChatCompletionMessageParam],
    response_model: type,
    task_type: str,
    max_tokens: int | None = None,
):
    runtime_selection = build_runtime_selection(
        model_registry=get_model_registry(),
        requested_model_id=None,
        task_type_value=task_type,
    )
    execution_plan = build_execution_plan(
        runtime_selection=runtime_selection,
        temperature=0.3,
        max_tokens=max_tokens,
        task_type=task_type,
    )
    return await execute_structured(
        execution_plan=execution_plan,
        response_model=response_model,
        messages=messages,
        schema_instruction=_build_schema_prompt(response_model),
        token_callback=token_callback_var.get(None),
        resolve_model=resolve_model,
        call_llm=_call_llm,
        call_llm_streaming=_call_llm_streaming,
        logger=logger,
    )


async def generate_outline(
    user_query: str,
    paper_context: str,
    language_name: str,
) -> DraftOutline:
    return await execute_task_completion(
        messages=[
            {
                "role": "system",
                "content": OUTLINE_GENERATION_SYSTEM.format(language_name=language_name),
            },
            {
                "role": "user",
                "content": DRAFT_USER_PROMPT.format(
                    user_query=user_query,
                    paper_context=paper_context,
                ),
            },
        ],
        response_model=DraftOutline,
        task_type="writing",
    )


async def generate_section(
    section_title: str,
    section_num: int,
    total_sections: int,
    outline_titles: list[str],
    user_query: str,
    paper_context: str,
    language_name: str,
    num_papers: int,
) -> ReviewSection:
    result = await execute_task_completion(
        messages=[
            {
                "role": "system",
                "content": SECTION_GENERATION_SYSTEM.format(
                    section_title=section_title,
                    section_num=section_num,
                    total_sections=total_sections,
                    outline_titles=", ".join(outline_titles),
                    language_name=language_name,
                    num_papers=num_papers,
                ),
            },
            {
                "role": "user",
                "content": DRAFT_USER_PROMPT.format(
                    user_query=user_query,
                    paper_context=paper_context,
                ),
            },
        ],
        response_model=ReviewSection,
        max_tokens=get_section_max_tokens(num_papers),
        task_type="writing",
    )
    return ReviewSection(heading=section_title, content=result.content)
