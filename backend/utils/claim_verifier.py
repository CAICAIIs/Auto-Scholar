import asyncio
import json
import logging
import re
from typing import Any

from pydantic import BaseModel

from backend.constants import CLAIM_BATCH_SIZE
from backend.prompts import (
    CLAIM_BATCH_EXTRACTION_SYSTEM,
    CLAIM_BATCH_EXTRACTION_USER,
    CLAIM_EXTRACTION_SYSTEM,
    CLAIM_EXTRACTION_USER,
    CLAIM_VERIFICATION_SYSTEM,
    CLAIM_VERIFICATION_USER,
)
from backend.schemas import (
    BatchClaimList,
    Claim,
    ClaimVerificationResult,
    ClaimVerificationSummary,
    DraftOutput,
    EntailmentLabel,
    PaperMetadata,
)
from backend.utils.llm_client import structured_completion

logger = logging.getLogger(__name__)

CITE_PATTERN = re.compile(r"\{cite:(\d+)\}")


class ClaimList(BaseModel):
    claims: list[str]


class VerificationOutput(BaseModel):
    label: str
    confidence: float
    evidence_snippet: str
    rationale: str


async def extract_claims_from_section(
    section_index: int,
    section_title: str,
    section_content: str,
) -> list[Claim]:
    if not CITE_PATTERN.search(section_content):
        return []

    result = await structured_completion(
        messages=[
            {"role": "system", "content": CLAIM_EXTRACTION_SYSTEM},
            {
                "role": "user",
                "content": CLAIM_EXTRACTION_USER.format(
                    section_title=section_title,
                    section_content=section_content,
                ),
            },
        ],
        response_model=ClaimList,
        temperature=0.1,
        task_type="qa",
    )

    claims: list[Claim] = []
    for i, claim_text in enumerate(result.claims):
        citation_indices = [int(m) for m in CITE_PATTERN.findall(claim_text)]
        if citation_indices:
            claims.append(
                Claim(
                    claim_id=f"s{section_index}_c{i}",
                    text=claim_text,
                    section_index=section_index,
                    citation_indices=citation_indices,
                )
            )

    return claims


async def _extract_claims_batch(
    section_groups: list[list[int]],
    sections: list[str],
) -> list[Claim]:
    if not section_groups:
        return []

    sections_data = []
    for section_group in section_groups:
        group_sections = [{"section_index": idx, "text": sections[idx]} for idx in section_group]
        sections_data.extend(group_sections)

    sections_json = json.dumps(sections_data)

    result = await structured_completion(
        messages=[
            {"role": "system", "content": CLAIM_BATCH_EXTRACTION_SYSTEM},
            {
                "role": "user",
                "content": CLAIM_BATCH_EXTRACTION_USER.format(sections_json=sections_json),
            },
        ],
        response_model=BatchClaimList,
        temperature=0.1,
        task_type="qa",
    )

    all_claims: list[Claim] = []
    for section_claim in result.sections_claims:
        section_index = section_claim.section_index
        for i, claim_text in enumerate(section_claim.claims):
            citation_indices = [int(m) for m in CITE_PATTERN.findall(claim_text)]
            if citation_indices:
                all_claims.append(
                    Claim(
                        claim_id=f"s{section_index}_c{i}",
                        text=claim_text,
                        section_index=section_index,
                        citation_indices=citation_indices,
                    )
                )

    return all_claims


async def _safe_extract_claims_batch(
    section_groups: list[list[int]],
    sections: list[str],
) -> list[Claim]:
    try:
        return await _extract_claims_batch(section_groups, sections)
    except Exception as e:
        logger.warning("Batch claim extraction failed: %s", e)
        return []


async def _safe_extract_claims(
    section_index: int,
    section_title: str,
    section_content: str,
) -> list[Claim]:
    try:
        return await extract_claims_from_section(section_index, section_title, section_content)
    except Exception as e:
        logger.warning("Failed to extract claims from section %d: %s", section_index, e)
        return []


async def extract_all_claims(draft: DraftOutput) -> list[Claim]:
    num_sections = len(draft.sections)

    if num_sections <= 1:
        tasks = [
            _safe_extract_claims(i, section.heading, section.content)
            for i, section in enumerate(draft.sections)
        ]
        results = await asyncio.gather(*tasks)

        all_claims: list[Claim] = []
        for claims_list in results:
            all_claims.extend(claims_list)

        return all_claims

    section_indices_with_citations: list[int] = []
    for i, section in enumerate(draft.sections):
        if CITE_PATTERN.search(section.content):
            section_indices_with_citations.append(i)

    if not section_indices_with_citations:
        return []

    all_claims = []

    batches: list[list[int]] = []
    for i in range(0, len(section_indices_with_citations), CLAIM_BATCH_SIZE):
        batch = section_indices_with_citations[i : i + CLAIM_BATCH_SIZE]
        if batch:
            batches.append(batch)

    for batch in batches:
        batch_sections = []
        for idx in batch:
            batch_sections.append(draft.sections[idx])

        batch_result = await _safe_extract_claims_batch(
            [batch], [s.content for s in batch_sections]
        )

        if batch_result:
            all_claims.extend(batch_result)
        else:
            for section_idx in batch:
                section = draft.sections[section_idx]
                fallback_result = await _safe_extract_claims(
                    section_idx, section.heading, section.content
                )
                all_claims.extend(fallback_result)

    return all_claims


def _get_paper_by_index(papers: list[PaperMetadata], index: int) -> PaperMetadata | None:
    if 1 <= index <= len(papers):
        return papers[index - 1]
    return None


async def verify_single_claim(
    claim: Claim,
    citation_index: int,
    paper: PaperMetadata,
    vector_store: Any | None = None,
) -> ClaimVerificationResult:
    paper_context = paper.abstract[:1000] if paper.abstract else ""

    if vector_store is not None:
        try:
            from backend.utils.clients import get_embedder

            embedder = await get_embedder()
            if embedder:
                claim_embedding = await embedder.embed_text(claim.text)

                search_results = await vector_store.search(
                    query_vector=claim_embedding,
                    limit=5,
                    score_threshold=0.7,
                    filter_dict={"must": [{"key": "paper_id", "match": {"value": paper.paper_id}}]},
                )

                if search_results:
                    relevant_chunks = []
                    for result in search_results:
                        chunk_text = result["payload"].get("chunk_text", "")
                        page_start = result["payload"].get("page_start")
                        page_end = result["payload"].get("page_end")
                        if chunk_text:
                            page_info = f" (pages {page_start}-{page_end})" if page_start else ""
                            relevant_chunks.append(f"{chunk_text}{page_info}")

                    if relevant_chunks:
                        paper_context = "\n\n".join(relevant_chunks[:3])
        except Exception as e:
            logger.warning("Failed to retrieve full-text context: %s", e)

    result = await structured_completion(
        messages=[
            {"role": "system", "content": CLAIM_VERIFICATION_SYSTEM},
            {
                "role": "user",
                "content": CLAIM_VERIFICATION_USER.format(
                    claim_text=claim.text,
                    citation_index=citation_index,
                    paper_title=paper.title,
                    paper_abstract=paper_context,
                    paper_contribution=paper.core_contribution or "Not available",
                ),
            },
        ],
        response_model=VerificationOutput,
        temperature=0.1,
        task_type="qa",
    )

    label_map: dict[str, EntailmentLabel] = {
        "entails": EntailmentLabel.ENTAILS,
        "insufficient": EntailmentLabel.INSUFFICIENT,
        "contradicts": EntailmentLabel.CONTRADICTS,
    }
    label = label_map.get(result.label.lower(), EntailmentLabel.INSUFFICIENT)

    return ClaimVerificationResult(
        claim_id=claim.claim_id,
        claim_text=claim.text,
        citation_index=citation_index,
        paper_title=paper.title,
        label=label,
        confidence=max(0.0, min(1.0, result.confidence)),
        evidence_snippet=result.evidence_snippet[:500],
        rationale=result.rationale[:200],
    )


async def verify_claims(
    claims: list[Claim],
    papers: list[PaperMetadata],
    concurrency: int = 2,
    vector_store: Any | None = None,
) -> list[ClaimVerificationResult]:
    verification_tasks: list[tuple[Claim, int, PaperMetadata]] = []

    for claim in claims:
        for citation_index in claim.citation_indices:
            paper = _get_paper_by_index(papers, citation_index)
            if paper:
                verification_tasks.append((claim, citation_index, paper))

    if not verification_tasks:
        return []

    semaphore = asyncio.Semaphore(concurrency)

    async def bounded_verify(
        claim: Claim, citation_index: int, paper: PaperMetadata
    ) -> ClaimVerificationResult | None:
        async with semaphore:
            try:
                return await verify_single_claim(claim, citation_index, paper, vector_store)
            except Exception as e:
                logger.warning(
                    "Failed to verify claim %s against paper %d: %s",
                    claim.claim_id,
                    citation_index,
                    e,
                )
                return None

    results = await asyncio.gather(*[bounded_verify(c, idx, p) for c, idx, p in verification_tasks])

    return [r for r in results if r is not None]


def summarize_verifications(
    claims: list[Claim],
    results: list[ClaimVerificationResult],
) -> ClaimVerificationSummary:
    entails = [r for r in results if r.label == EntailmentLabel.ENTAILS]
    insufficient = [r for r in results if r.label == EntailmentLabel.INSUFFICIENT]
    contradicts = [r for r in results if r.label == EntailmentLabel.CONTRADICTS]

    failed = insufficient + contradicts

    return ClaimVerificationSummary(
        total_claims=len(claims),
        total_verifications=len(results),
        entails_count=len(entails),
        insufficient_count=len(insufficient),
        contradicts_count=len(contradicts),
        failed_verifications=failed,
    )


async def verify_draft_citations(
    draft: DraftOutput,
    papers: list[PaperMetadata],
    concurrency: int = 2,
    vector_store: Any | None = None,
) -> tuple[list[Claim], ClaimVerificationSummary]:
    logger.info("Extracting claims from draft with %d sections", len(draft.sections))
    claims = await extract_all_claims(draft)
    logger.info("Extracted %d claims with citations", len(claims))

    if not claims:
        return [], ClaimVerificationSummary(
            total_claims=0,
            total_verifications=0,
            entails_count=0,
            insufficient_count=0,
            contradicts_count=0,
            failed_verifications=[],
        )

    logger.info("Verifying claims against %d papers", len(papers))
    results = await verify_claims(claims, papers, concurrency, vector_store)
    logger.info("Completed %d verifications", len(results))

    summary = summarize_verifications(claims, results)
    return claims, summary
