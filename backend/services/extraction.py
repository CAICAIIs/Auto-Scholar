import asyncio

from backend.models.internal import ContributionExtraction, StructuredExtractionResult
from backend.prompts import (
    CONTRIBUTION_EXTRACTION_SYSTEM,
    CONTRIBUTION_EXTRACTION_USER,
    STRUCTURED_EXTRACTION_SYSTEM,
    STRUCTURED_EXTRACTION_USER,
)
from backend.schemas import PaperMetadata, StructuredContribution
from backend.utils.llm_client import structured_completion


async def extract_contribution(paper: PaperMetadata) -> PaperMetadata:
    core_task = structured_completion(
        messages=[
            {"role": "system", "content": CONTRIBUTION_EXTRACTION_SYSTEM},
            {
                "role": "user",
                "content": CONTRIBUTION_EXTRACTION_USER.format(
                    title=paper.title,
                    year=paper.year,
                    abstract=paper.abstract,
                ),
            },
        ],
        response_model=ContributionExtraction,
        task_type="extraction",
    )

    structured_task = structured_completion(
        messages=[
            {"role": "system", "content": STRUCTURED_EXTRACTION_SYSTEM},
            {
                "role": "user",
                "content": STRUCTURED_EXTRACTION_USER.format(
                    title=paper.title,
                    year=paper.year,
                    abstract=paper.abstract,
                ),
            },
        ],
        response_model=StructuredExtractionResult,
        task_type="extraction",
    )

    core_result, structured_result = await asyncio.gather(core_task, structured_task)

    if not core_result.core_contribution or not core_result.core_contribution.strip():
        raise ValueError("LLM returned empty core_contribution")

    structured_contrib = StructuredContribution(
        problem=structured_result.problem or None,
        method=structured_result.method or None,
        novelty=structured_result.novelty or None,
        dataset=structured_result.dataset or None,
        baseline=structured_result.baseline or None,
        results=structured_result.results or None,
        limitations=structured_result.limitations or None,
        future_work=structured_result.future_work or None,
    )

    return paper.model_copy(
        update={
            "core_contribution": core_result.core_contribution,
            "structured_contribution": structured_contrib,
        }
    )
