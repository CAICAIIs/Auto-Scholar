import re

from backend.evaluation.schemas import CitationPrecisionResult, CitationRecallResult
from backend.schemas import DraftOutput, PaperMetadata

CITATION_PATTERN = re.compile(r"\{cite:(\d+)\}")


def extract_citation_indices(text: str) -> list[int]:
    return [int(m.group(1)) for m in CITATION_PATTERN.finditer(text)]


def calculate_citation_precision(draft: DraftOutput, num_approved: int) -> CitationPrecisionResult:
    all_indices: list[int] = []
    for section in draft.sections:
        all_indices.extend(extract_citation_indices(section.content))

    valid_count = 0
    invalid_indices: list[int] = []

    for idx in all_indices:
        if 1 <= idx <= num_approved:
            valid_count += 1
        else:
            if idx not in invalid_indices:
                invalid_indices.append(idx)

    return CitationPrecisionResult(
        total_citations=len(all_indices),
        valid_citations=valid_count,
        invalid_indices=sorted(invalid_indices),
    )


def calculate_citation_recall(
    draft: DraftOutput, approved_papers: list[PaperMetadata]
) -> CitationRecallResult:
    num_approved = len(approved_papers)
    if num_approved == 0:
        return CitationRecallResult(
            total_approved=0,
            cited_count=0,
            uncited_indices=[],
        )

    cited_indices: set[int] = set()
    for section in draft.sections:
        for idx in extract_citation_indices(section.content):
            if 1 <= idx <= num_approved:
                cited_indices.add(idx)

    uncited = [i for i in range(1, num_approved + 1) if i not in cited_indices]

    return CitationRecallResult(
        total_approved=num_approved,
        cited_count=len(cited_indices),
        uncited_indices=uncited,
    )
