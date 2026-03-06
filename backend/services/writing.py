from backend.constants import get_section_max_tokens
from backend.prompts import (
    DRAFT_USER_PROMPT,
    OUTLINE_GENERATION_SYSTEM,
    SECTION_GENERATION_SYSTEM,
)
from backend.schemas import DraftOutline, ReviewSection
from backend.utils.llm_client import structured_completion


async def generate_outline(
    user_query: str,
    paper_context: str,
    language_name: str,
) -> DraftOutline:
    return await structured_completion(
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
    result = await structured_completion(
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
