"""Citation normalization utilities.

Extracts {cite:N} placeholders from draft sections and replaces them with [N] format.
Shared by the SSE stream completion handler and export utilities.
"""

import logging
import re

from backend.schemas import DraftOutput, PaperMetadata

logger = logging.getLogger(__name__)


def normalize_draft_citations(
    draft: DraftOutput,
    approved_papers: list[PaperMetadata],
) -> DraftOutput:
    """Replace {cite:N} placeholders with [N] and populate cited_paper_ids per section.

    Args:
        draft: The raw draft with {cite:N} placeholders.
        approved_papers: Ordered list of approved papers (index 1-based).

    Returns:
        A new DraftOutput with normalized citations.
    """
    max_index = len(approved_papers)
    index_to_id = {i + 1: p.paper_id for i, p in enumerate(approved_papers)}
    pattern = r"\{cite:(\d+)\}"

    for section in draft.sections:

        def replace_match(m: re.Match[str]) -> str:
            idx = int(m.group(1))
            if 1 <= idx <= max_index:
                return f"[{idx}]"
            logger.warning("Citation index %d out of range (1-%d), removing", idx, max_index)
            return ""

        section.content = re.sub(pattern, replace_match, section.content)
        cited_indices = [
            int(n) for n in re.findall(r"\[(\d+)\]", section.content) if 1 <= int(n) <= max_index
        ]
        section.cited_paper_ids = [index_to_id[idx] for idx in sorted(set(cited_indices))]

    return draft
