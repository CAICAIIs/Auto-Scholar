import asyncio
import logging
import re
from typing import Any

from pydantic import BaseModel

from app.constants import (
    MAX_KEYWORDS,
    PAPERS_PER_QUERY,
    LLM_CONCURRENCY,
    FULLTEXT_CONCURRENCY,
    MAX_CONVERSATION_TURNS,
    get_draft_max_tokens,
)
from app.schemas import PaperMetadata, DraftOutput, PaperSource, ConversationMessage, MessageRole
from app.state import AgentState
from app.utils.llm_client import structured_completion
from app.utils.scholar_api import search_papers_multi_source
from app.utils.fulltext_api import enrich_papers_with_fulltext

logger = logging.getLogger(__name__)


class KeywordPlan(BaseModel):
    keywords: list[str]


class ContributionExtraction(BaseModel):
    core_contribution: str


def _build_conversation_context(messages: list[ConversationMessage], max_turns: int = MAX_CONVERSATION_TURNS) -> str:
    if not messages:
        return ""
    recent = messages[-max_turns * 2:] if len(messages) > max_turns * 2 else messages
    lines = []
    for msg in recent:
        role_label = "User" if msg.role == MessageRole.USER else "Assistant"
        lines.append(f"{role_label}: {msg.content}")
    return "\n".join(lines)


async def plan_node(state: AgentState) -> dict[str, Any]:
    user_query = state["user_query"]
    is_continuation = state.get("is_continuation", False)
    messages = state.get("messages", [])
    
    logger.info("plan_node: decomposing query: %s (continuation: %s)", user_query, is_continuation)

    system_content = (
        "Generate 3-5 English search keywords for academic paper search.\n\n"
        "Requirements:\n"
        "- Each keyword: 2-4 words, specific enough to filter results\n"
        "- Cover different angles: core concept, methodology, application domain\n"
        "- Avoid overly broad single words (e.g. 'learning', 'analysis', 'model')"
    )
    
    if is_continuation and messages:
        conversation_context = _build_conversation_context(messages)
        system_content += (
            "\n\nThis is a follow-up request. Consider the conversation history "
            "when generating keywords to find additional relevant papers.\n"
            f"Conversation history:\n{conversation_context}"
        )

    result = await structured_completion(
        messages=[
            {"role": "system", "content": system_content},
            {"role": "user", "content": user_query},
        ],
        response_model=KeywordPlan,
    )

    keywords = result.keywords[:MAX_KEYWORDS]
    log_msg = f"Generated {len(keywords)} search keywords: {keywords}"
    logger.info("plan_node: %s", log_msg)
    return {"search_keywords": keywords, "logs": [log_msg]}


async def search_node(state: AgentState) -> dict[str, Any]:
    keywords = state.get("search_keywords", [])
    if not keywords:
        log_msg = "No search keywords available, skipping search"
        logger.warning("search_node: %s", log_msg)
        return {"candidate_papers": [], "logs": [log_msg]}

    sources = state.get("search_sources", [PaperSource.SEMANTIC_SCHOLAR])
    source_names = [s.value for s in sources]
    
    logger.info("search_node: searching %d keywords across %s", len(keywords), source_names)
    papers = await search_papers_multi_source(keywords, sources=sources, limit_per_query=PAPERS_PER_QUERY)

    log_msg = f"Found {len(papers)} unique papers across {len(keywords)} queries from {source_names}"
    logger.info("search_node: %s", log_msg)
    return {"candidate_papers": papers, "logs": [log_msg]}


async def _extract_contribution(paper: PaperMetadata) -> PaperMetadata:
    result = await structured_completion(
        messages=[
            {
                "role": "system",
                "content": (
                    "Extract the paper's core contribution in ONE sentence (15-30 words).\n"
                    "Format: \"[Novel method/key finding] that [achieves/enables] [specific outcome]\"\n"
                    "If abstract is vague, infer from title. Output in English.\n"
                    "CRITICAL: You MUST return a non-empty string for core_contribution."
                ),
            },
            {
                "role": "user",
                "content": (
                    f"Title: {paper.title}\n"
                    f"Year: {paper.year}\n"
                    f"Abstract: {paper.abstract}"
                ),
            },
        ],
        response_model=ContributionExtraction,
    )

    if not result.core_contribution or not result.core_contribution.strip():
        raise ValueError("LLM returned empty core_contribution")

    return paper.model_copy(update={"core_contribution": result.core_contribution})


async def read_and_extract_node(state: AgentState) -> dict[str, Any]:
    candidates = state.get("candidate_papers", [])
    approved = [p for p in candidates if p.is_approved]

    if not approved:
        log_msg = "No approved papers to process"
        logger.warning("read_and_extract_node: %s", log_msg)
        return {"approved_papers": [], "logs": [log_msg]}

    logger.info("read_and_extract_node: extracting contributions from %d papers", len(approved))

    semaphore = asyncio.Semaphore(LLM_CONCURRENCY)
    async def extract_with_limit(paper: PaperMetadata) -> PaperMetadata:
        async with semaphore:
            return await _extract_contribution(paper)

    tasks = [extract_with_limit(p) for p in approved]
    results = await asyncio.gather(*tasks, return_exceptions=True)

    extracted: list[PaperMetadata] = []
    failed_count = 0
    for r, paper in zip(results, approved):
        if isinstance(r, BaseException):
            logger.error(
                "ContributionExtraction failed for paper '%s' (ID: %s): %s",
                paper.title[:60],
                paper.paper_id,
                r,
            )
            failed_count += 1
            continue
        extracted.append(r)

    log_msg = f"Extracted contributions from {len(extracted)} papers"
    if failed_count:
        log_msg += f" ({failed_count} failed - check logs for details)"
    logger.info("read_and_extract_node: %s", log_msg)
    
    logs = [log_msg]
    
    papers_needing_pdf = [p for p in extracted if not p.pdf_url]
    if papers_needing_pdf:
        logger.info("read_and_extract_node: enriching %d papers with full-text URLs", len(papers_needing_pdf))
        try:
            enriched = await enrich_papers_with_fulltext(extracted, concurrency=FULLTEXT_CONCURRENCY)
            pdf_count = sum(1 for p in enriched if p.pdf_url)
            pdf_log = f"Found full-text PDFs for {pdf_count}/{len(enriched)} papers"
            logger.info("read_and_extract_node: %s", pdf_log)
            logs.append(pdf_log)
            extracted = enriched
        except Exception as e:
            logger.warning("read_and_extract_node: full-text enrichment failed: %s", e)
    
    return {"approved_papers": extracted, "logs": logs}


def _build_paper_context(papers: list[PaperMetadata]) -> str:
    lines: list[str] = []
    for i, p in enumerate(papers, 1):
        paper_info = [
            f"[{i}] {p.title} (Year: {p.year or 'N/A'})",
            f"    Authors: {', '.join(p.authors[:3])}{'...' if len(p.authors) > 3 else ''}",
            f"    Contribution: {p.core_contribution}",
        ]
        if p.abstract:
            abstract_preview = p.abstract[:200] + "..." if len(p.abstract) > 200 else p.abstract
            paper_info.append(f"    Abstract: {abstract_preview}")
        lines.append("\n".join(paper_info))
    return "\n\n".join(lines)


async def draft_node(state: AgentState) -> dict[str, Any]:
    approved = state.get("approved_papers", [])
    papers_with_contributions = [p for p in approved if p.core_contribution]
    output_language = state.get("output_language", "en")
    is_continuation = state.get("is_continuation", False)
    messages = state.get("messages", [])

    if not papers_with_contributions:
        log_msg = "No papers with extracted contributions, cannot draft review"
        logger.warning("draft_node: %s", log_msg)
        return {"final_draft": None, "logs": [log_msg]}

    paper_context = _build_paper_context(papers_with_contributions)
    user_query = state["user_query"]
    qa_errors = state.get("qa_errors", [])
    retry_count = state.get("retry_count", 0)

    is_retry = retry_count > 0 and qa_errors
    if is_retry:
        logger.info("draft_node: RETRY %d - fixing %d QA errors", retry_count, len(qa_errors))
    elif is_continuation:
        logger.info("draft_node: CONTINUATION - updating draft based on: %s", user_query[:100])
    else:
        logger.info("draft_node: drafting review with %d papers in %s", len(papers_with_contributions), output_language)

    language_name = "Chinese" if output_language == "zh" else "English"
    num_papers = len(papers_with_contributions)

    system_prompt = (
        f"Write a structured literature review with 4-6 thematic sections "
        f"in formal academic {language_name}.\n\n"
        "REQUIRED SECTIONS:\n"
        "1. Introduction/Background - overview of the research area\n"
        "2-4. Thematic sections - group papers by methodology, approach, or application\n"
        "5. Methodology Comparison - compare and contrast the methods used across papers "
        "(include a comparison of strengths, limitations, datasets, and key findings)\n"
        "6. Conclusion/Future Directions - summarize insights and identify research gaps\n\n"
        "CITATION RULES:\n"
        f"- Use {{cite:N}} to reference papers, where N is the number shown "
        f"in brackets in the paper list (1 to {num_papers}).\n"
        f"- Example: \"Smith et al. {{cite:1}} proposed X, while Jones {{cite:3}} extended Y.\"\n"
        f"- You MUST cite ALL {num_papers} papers. Do NOT invent numbers outside 1-{num_papers}."
    )

    if is_continuation and messages:
        conversation_context = _build_conversation_context(messages)
        existing_draft = state.get("final_draft")
        existing_draft_summary = ""
        if existing_draft:
            section_titles = [s.heading for s in existing_draft.sections]
            existing_draft_summary = f"\nExisting draft title: {existing_draft.title}\nSections: {', '.join(section_titles)}"
        
        system_prompt += (
            f"\n\nThis is a REVISION request. The user wants to modify the existing draft."
            f"{existing_draft_summary}\n"
            f"User's modification request: {user_query}\n\n"
            f"Conversation history:\n{conversation_context}\n\n"
            "Please revise the draft according to the user's request while maintaining "
            "proper citations and academic quality."
        )

    if is_retry:
        top_errors = qa_errors[:3]
        error_list = "\n".join(f"- {e}" for e in top_errors)
        system_prompt += (
            f"\n\nPREVIOUS ATTEMPT FAILED ({len(qa_errors)} errors). Fix these:\n"
            f"{error_list}\n"
            f"REMINDER: Valid citation numbers are 1 to {num_papers}. "
            f"Use ONLY {{cite:1}} through {{cite:{num_papers}}}. "
            f"Every paper (1-{num_papers}) MUST be cited at least once."
        )

    draft = await structured_completion(
        messages=[
            {"role": "system", "content": system_prompt},
            {
                "role": "user",
                "content": (
                    f"Research Topic: {user_query}\n\n"
                    f"Papers for Review:\n{paper_context}"
                ),
            },
        ],
        response_model=DraftOutput,
        max_tokens=get_draft_max_tokens(num_papers),
    )

    cite_pattern = re.compile(r'\{cite:(\d+)\}')
    all_cited_indices: set[int] = set()
    for section in draft.sections:
        all_cited_indices.update({int(m) for m in cite_pattern.findall(section.content)})

    out_of_bounds = [idx for idx in all_cited_indices if idx < 1 or idx > num_papers]
    if out_of_bounds:
        logger.warning(
            "draft_node: Found out-of-bounds citations: %s (valid range: 1-%d)",
            sorted(out_of_bounds),
            num_papers,
        )

    log_msg = f"Draft complete: '{draft.title}' with {len(draft.sections)} sections, {len(all_cited_indices)} unique citations"
    if is_retry:
        log_msg += f" (retry {retry_count})"
    logger.info("draft_node: %s", log_msg)
    return {"final_draft": draft, "logs": [log_msg]}


async def qa_evaluator_node(state: AgentState) -> dict[str, Any]:
    draft = state.get("final_draft")
    if draft is None:
        log_msg = "QA skipped: no draft to evaluate"
        logger.warning("qa_evaluator_node: %s", log_msg)
        return {"qa_errors": [], "logs": [log_msg]}

    approved = state.get("approved_papers", [])
    num_papers = len(approved)
    valid_indices: set[int] = set(range(1, num_papers + 1))

    errors: list[str] = []
    all_cited_indices: set[int] = set()

    cite_pattern = re.compile(r'\{cite:(\d+)\}')

    for section_idx, section in enumerate(draft.sections):
        cited_in_content = {int(m) for m in cite_pattern.findall(section.content)}
        all_cited_indices.update(cited_in_content)

        for idx in cited_in_content:
            if idx not in valid_indices:
                errors.append(
                    f"Section {section_idx+1}: Hallucinated citation index "
                    f"{idx} (valid range: 1-{num_papers})"
                )

        if not cited_in_content:
            errors.append(
                f"Section {section_idx+1}: No citations found in content"
            )

    missing = valid_indices - all_cited_indices
    for idx in sorted(missing):
        errors.append(f"Missing citation: paper [{idx}] was approved but not cited")

    retry_count = state.get("retry_count", 0)

    if errors:
        retry_count += 1
        log_msg = f"QA failed with {len(errors)} errors (retry {retry_count}/3): {errors[:3]}"
        logger.warning("qa_evaluator_node: %s", log_msg)
        return {"qa_errors": errors, "retry_count": retry_count, "logs": [log_msg]}

    log_msg = "QA passed: all citations verified"
    logger.info("qa_evaluator_node: %s", log_msg)
    return {"qa_errors": [], "retry_count": retry_count, "logs": [log_msg]}
