import asyncio
import logging
import re
import time
from typing import Any

from pydantic import BaseModel

from backend.constants import (
    CLAIM_VERIFICATION_CONCURRENCY,
    CLAIM_VERIFICATION_ENABLED,
    CONTEXT_MAX_PAPERS,
    CONTEXT_OVERFLOW_WARNING_THRESHOLD,
    CONTEXT_TOKEN_BUDGET,
    FULLTEXT_CONCURRENCY,
    LLM_CONCURRENCY,
    MAX_CONVERSATION_TURNS,
    MAX_KEYWORDS,
    MIN_ENTAILMENT_RATIO,
    PAPERS_PER_QUERY,
    get_draft_max_tokens,
    get_section_max_tokens,
)
from backend.prompts import (
    CONTRIBUTION_EXTRACTION_SYSTEM,
    CONTRIBUTION_EXTRACTION_USER,
    DRAFT_GENERATION_SYSTEM,
    DRAFT_REFLECTION_RETRY_ADDENDUM,
    DRAFT_RETRY_ADDENDUM,
    DRAFT_REVISION_ADDENDUM,
    DRAFT_USER_PROMPT,
    KEYWORD_GENERATION_CONTINUATION,
    KEYWORD_GENERATION_SYSTEM,
    OUTLINE_GENERATION_SYSTEM,
    PLANNER_COT_SYSTEM,
    REFLECTION_SYSTEM,
    REFLECTION_USER,
    SECTION_GENERATION_SYSTEM,
    STRUCTURED_EXTRACTION_SYSTEM,
    STRUCTURED_EXTRACTION_USER,
)
from backend.schemas import (
    ConversationMessage,
    DraftOutline,
    DraftOutput,
    MessageRole,
    MethodComparisonEntry,
    PaperMetadata,
    PaperSource,
    Reflection,
    ResearchPlan,
    ReviewSection,
    StructuredContribution,
)
from backend.state import AgentState
from backend.utils.claim_verifier import verify_draft_citations
from backend.utils.fulltext_api import enrich_papers_with_fulltext
from backend.utils.llm_client import structured_completion
from backend.utils.scholar_api import search_by_plan, search_papers_multi_source

logger = logging.getLogger(__name__)


class KeywordPlan(BaseModel):
    keywords: list[str]


class ContributionExtraction(BaseModel):
    core_contribution: str


class StructuredExtractionResult(BaseModel):
    problem: str | None = None
    method: str | None = None
    novelty: str | None = None
    dataset: str | None = None
    baseline: str | None = None
    results: str | None = None
    limitations: str | None = None
    future_work: str | None = None


def _build_conversation_context(
    messages: list[ConversationMessage], max_turns: int = MAX_CONVERSATION_TURNS
) -> str:
    if not messages:
        return ""
    recent = messages[-max_turns * 2 :] if len(messages) > max_turns * 2 else messages
    lines = []
    for msg in recent:
        role_label = "User" if msg.role == MessageRole.USER else "Assistant"
        lines.append(f"{role_label}: {msg.content}")
    return "\n".join(lines)


COT_QUERY_MIN_LENGTH = 10


async def planner_agent(state: AgentState) -> dict[str, Any]:
    user_query = state["user_query"]
    is_continuation = state.get("is_continuation", False)
    messages = state.get("messages", [])
    use_cot = len(user_query.strip()) >= COT_QUERY_MIN_LENGTH and not is_continuation

    logger.info(
        "planner_agent: decomposing query: %s (continuation: %s, cot: %s)",
        user_query,
        is_continuation,
        use_cot,
    )

    if use_cot:
        system_content = PLANNER_COT_SYSTEM
        start_time = time.perf_counter()
        plan = await structured_completion(
            messages=[
                {"role": "system", "content": system_content},
                {"role": "user", "content": user_query},
            ],
            response_model=ResearchPlan,
        )
        elapsed = time.perf_counter() - start_time
        logger.info("planner_agent: CoT planning completed in %.2fs", elapsed)

        all_keywords: list[str] = []
        for sq in plan.sub_questions:
            all_keywords.extend(sq.keywords)
        keywords = list(dict.fromkeys(all_keywords))[:MAX_KEYWORDS]

        logs = [
            f"Research plan: {len(plan.sub_questions)} sub-questions identified",
            f"Reasoning: {plan.reasoning[:200]}...",
            f"Generated {len(keywords)} search keywords: {keywords}",
        ]

        return {
            "search_keywords": keywords,
            "research_plan": plan,
            "logs": logs,
            "current_agent": "planner",
            "agent_handoffs": ["→planner"],
        }

    system_content = KEYWORD_GENERATION_SYSTEM

    if is_continuation and messages:
        conversation_context = _build_conversation_context(messages)
        system_content += KEYWORD_GENERATION_CONTINUATION.format(
            conversation_context=conversation_context
        )

    start_time = time.perf_counter()
    result = await structured_completion(
        messages=[
            {"role": "system", "content": system_content},
            {"role": "user", "content": user_query},
        ],
        response_model=KeywordPlan,
    )
    elapsed = time.perf_counter() - start_time
    logger.info("planner_agent: LLM call completed in %.2fs", elapsed)

    keywords = result.keywords[:MAX_KEYWORDS]
    log_msg = f"Generated {len(keywords)} search keywords: {keywords}"
    logger.info("planner_agent: %s", log_msg)
    return {
        "search_keywords": keywords,
        "research_plan": None,
        "logs": [log_msg],
        "current_agent": "planner",
        "agent_handoffs": ["→planner"],
    }


async def retriever_agent(state: AgentState) -> dict[str, Any]:
    keywords = state.get("search_keywords", [])
    if not keywords:
        log_msg = "No search keywords available, skipping search"
        logger.warning("retriever_agent: %s", log_msg)
        return {
            "candidate_papers": [],
            "logs": [log_msg],
            "current_agent": "retriever",
            "agent_handoffs": ["planner→retriever"],
        }

    research_plan = state.get("research_plan")
    sources = state.get(
        "search_sources",
        [
            PaperSource.SEMANTIC_SCHOLAR,
            PaperSource.ARXIV,
            PaperSource.PUBMED,
        ],
    )

    if research_plan and research_plan.sub_questions:
        logger.info(
            "retriever_agent: plan-aware search with %d sub-questions",
            len(research_plan.sub_questions),
        )
        start_time = time.perf_counter()
        papers = await search_by_plan(
            research_plan, default_limit=PAPERS_PER_QUERY, allowed_sources=sources
        )
        elapsed = time.perf_counter() - start_time
        logger.info("retriever_agent: plan-aware search completed in %.2fs", elapsed)

        sq_sources = [sq.preferred_source.value for sq in research_plan.sub_questions]
        log_msg = (
            f"Found {len(papers)} unique papers from {len(research_plan.sub_questions)} "
            f"sub-questions (sources: {sq_sources})"
        )
    else:
        source_names = [s.value for s in sources]
        logger.info("retriever_agent: searching %d keywords across %s", len(keywords), source_names)
        start_time = time.perf_counter()
        papers = await search_papers_multi_source(
            keywords, sources=sources, limit_per_query=PAPERS_PER_QUERY
        )
        elapsed = time.perf_counter() - start_time
        logger.info("retriever_agent: paper search completed in %.2fs", elapsed)

        log_msg = (
            f"Found {len(papers)} unique papers across {len(keywords)} queries from {source_names}"
        )

    logger.info("retriever_agent: %s", log_msg)
    return {
        "candidate_papers": papers,
        "logs": [log_msg],
        "current_agent": "retriever",
        "agent_handoffs": ["planner→retriever"],
    }


async def _extract_contribution(paper: PaperMetadata) -> PaperMetadata:
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


async def extractor_agent(state: AgentState) -> dict[str, Any]:
    candidates = state.get("candidate_papers", [])
    approved = [p for p in candidates if p.is_approved]

    if not approved:
        log_msg = "No approved papers to process"
        logger.warning("extractor_agent: %s", log_msg)
        return {
            "approved_papers": [],
            "selected_papers": [],
            "logs": [log_msg],
            "current_agent": "extractor",
            "agent_handoffs": ["retriever→extractor"],
        }

    research_plan = state.get("research_plan")
    if research_plan and research_plan.sub_questions:
        approved_ordered = _prioritize_by_sub_questions(approved, research_plan)
    else:
        approved_ordered = approved

    selected = approved_ordered[:CONTEXT_MAX_PAPERS]

    if len(approved) > CONTEXT_MAX_PAPERS:
        logger.info(
            "extractor_agent: selected %d/%d approved papers for extraction",
            len(selected),
            len(approved),
        )

    logger.info("extractor_agent: extracting contributions from %d papers", len(selected))

    semaphore = asyncio.Semaphore(LLM_CONCURRENCY)

    async def extract_with_limit(paper: PaperMetadata) -> PaperMetadata:
        async with semaphore:
            return await _extract_contribution(paper)

    tasks = [extract_with_limit(p) for p in selected]
    results = await asyncio.gather(*tasks, return_exceptions=True)

    extracted: list[PaperMetadata] = []
    failed_count = 0
    for r, paper in zip(results, selected):
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
    if len(approved) > len(selected):
        log_msg += f" (selected from {len(approved)} approved)"
    if failed_count:
        log_msg += f" ({failed_count} failed)"
    logger.info("extractor_agent: %s", log_msg)

    logs = [log_msg]

    papers_needing_pdf = [p for p in extracted if not p.pdf_url]
    if papers_needing_pdf:
        logger.info(
            "extractor_agent: enriching %d papers with full-text URLs",
            len(papers_needing_pdf),
        )
        try:
            enriched = await enrich_papers_with_fulltext(
                extracted, concurrency=FULLTEXT_CONCURRENCY
            )
            pdf_count = sum(1 for p in enriched if p.pdf_url)
            pdf_log = f"Found full-text PDFs for {pdf_count}/{len(enriched)} papers"
            logger.info("extractor_agent: %s", pdf_log)
            logs.append(pdf_log)
            extracted = enriched
        except Exception as e:
            logger.warning("extractor_agent: full-text enrichment failed: %s", e)

    return {
        "approved_papers": approved,
        "selected_papers": extracted,
        "logs": logs,
        "current_agent": "extractor",
        "agent_handoffs": ["retriever→extractor"],
    }


def _estimate_paper_tokens(paper: PaperMetadata) -> int:
    parts = [paper.title, paper.core_contribution or ""]
    sc = paper.structured_contribution
    if sc:
        for field in (
            sc.problem,
            sc.method,
            sc.novelty,
            sc.dataset,
            sc.baseline,
            sc.results,
            sc.limitations,
            sc.future_work,
        ):
            if field:
                parts.append(field)
    elif paper.abstract:
        parts.append(paper.abstract[:200])
    text = " ".join(parts)
    return max(int(len(text.split()) * 1.3), 20)


def _prioritize_by_sub_questions(
    papers: list[PaperMetadata],
    research_plan: ResearchPlan,
) -> list[PaperMetadata]:
    reserved: list[PaperMetadata] = []
    remaining = list(papers)

    for sq in sorted(research_plan.sub_questions, key=lambda s: s.priority):
        best = _find_best_keyword_match(remaining, sq.keywords)
        if best:
            reserved.append(best)
            remaining.remove(best)

    return reserved + remaining


def _find_best_keyword_match(
    papers: list[PaperMetadata],
    keywords: list[str],
) -> PaperMetadata | None:
    if not papers or not keywords:
        return None
    lower_keywords = [k.lower() for k in keywords]

    def score(p: PaperMetadata) -> int:
        title_lower = p.title.lower()
        return sum(1 for kw in lower_keywords if kw in title_lower)

    scored = [(score(p), p) for p in papers]
    scored.sort(key=lambda x: x[0], reverse=True)
    return scored[0][1] if scored[0][0] > 0 else papers[0]


def _build_paper_context(
    papers: list[PaperMetadata],
    research_plan: ResearchPlan | None = None,
    token_budget: int = CONTEXT_TOKEN_BUDGET,
) -> str:
    if not papers:
        return ""

    if len(papers) > CONTEXT_OVERFLOW_WARNING_THRESHOLD:
        logger.warning(
            "paper count %d exceeds warning threshold %d",
            len(papers),
            CONTEXT_OVERFLOW_WARNING_THRESHOLD,
        )

    if len(papers) > CONTEXT_MAX_PAPERS:
        logger.warning(
            "paper count %d exceeds hard limit %d, truncating",
            len(papers),
            CONTEXT_MAX_PAPERS,
        )
        papers = papers[:CONTEXT_MAX_PAPERS]

    if research_plan and research_plan.sub_questions:
        papers = _prioritize_by_sub_questions(papers, research_plan)

    selected: list[PaperMetadata] = []
    estimated_tokens = 0
    for p in papers:
        paper_tokens = _estimate_paper_tokens(p)
        if estimated_tokens + paper_tokens > token_budget and selected:
            logger.info(
                "context budget reached: %d/%d tokens, %d/%d papers included",
                estimated_tokens,
                token_budget,
                len(selected),
                len(papers),
            )
            break
        selected.append(p)
        estimated_tokens += paper_tokens

    lines: list[str] = []
    for i, p in enumerate(selected, 1):
        paper_info = [
            f"[{i}] {p.title} (Year: {p.year or 'N/A'})",
            f"    Authors: {', '.join(p.authors[:3])}{'...' if len(p.authors) > 3 else ''}",
            f"    Contribution: {p.core_contribution}",
        ]

        sc = p.structured_contribution
        if sc:
            if sc.problem:
                paper_info.append(f"    Problem: {sc.problem}")
            if sc.method:
                paper_info.append(f"    Method: {sc.method}")
            if sc.novelty:
                paper_info.append(f"    Novelty: {sc.novelty}")
            if sc.dataset:
                paper_info.append(f"    Dataset: {sc.dataset}")
            if sc.baseline:
                paper_info.append(f"    Baseline: {sc.baseline}")
            if sc.results:
                paper_info.append(f"    Results: {sc.results}")
            if sc.limitations:
                paper_info.append(f"    Limitations: {sc.limitations}")
            if sc.future_work:
                paper_info.append(f"    Future Work: {sc.future_work}")
        elif p.abstract:
            abstract_preview = p.abstract[:200] + "..." if len(p.abstract) > 200 else p.abstract
            paper_info.append(f"    Abstract: {abstract_preview}")

        lines.append("\n".join(paper_info))
    return "\n\n".join(lines)


def build_comparison_table(papers: list[PaperMetadata]) -> list[MethodComparisonEntry]:
    entries: list[MethodComparisonEntry] = []
    for i, p in enumerate(papers, 1):
        sc = p.structured_contribution
        title = p.title[:60] + "..." if len(p.title) > 60 else p.title
        entries.append(
            MethodComparisonEntry(
                paper_index=i,
                title=title,
                method=sc.method if sc else None,
                dataset=sc.dataset if sc else None,
                baseline=sc.baseline if sc else None,
                results=sc.results if sc else None,
            )
        )
    return entries


async def _generate_outline(
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
    )


async def _generate_section(
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
    )
    return ReviewSection(heading=section_title, content=result.content)


async def writer_agent(state: AgentState) -> dict[str, Any]:
    approved = state.get("approved_papers", [])
    papers_with_contributions = [p for p in approved if p.core_contribution]
    output_language = state.get("output_language", "en")
    is_continuation = state.get("is_continuation", False)
    messages = state.get("messages", [])

    if not papers_with_contributions:
        log_msg = "No papers with extracted contributions, cannot draft review"
        logger.warning("writer_agent: %s", log_msg)
        return {
            "final_draft": None,
            "logs": [log_msg],
            "current_agent": "writer",
            "agent_handoffs": ["extractor→writer"],
        }

    paper_context = _build_paper_context(
        papers_with_contributions,
        research_plan=state.get("research_plan"),
    )
    user_query = state["user_query"]
    qa_errors = state.get("qa_errors", [])
    retry_count = state.get("retry_count", 0)
    language_name = "Chinese" if output_language == "zh" else "English"
    num_papers = len(papers_with_contributions)

    is_retry = retry_count > 0 and qa_errors
    use_single_call = is_retry or is_continuation

    if use_single_call:
        if is_retry:
            logger.info("writer_agent: RETRY %d - fixing %d QA errors", retry_count, len(qa_errors))
        else:
            logger.info(
                "writer_agent: CONTINUATION - updating draft based on: %s", user_query[:100]
            )

        system_prompt = DRAFT_GENERATION_SYSTEM.format(
            language_name=language_name,
            num_papers=num_papers,
        )

        if is_continuation and messages:
            conversation_context = _build_conversation_context(messages)
            existing_draft = state.get("final_draft")
            existing_draft_summary = ""
            if existing_draft:
                section_titles = [s.heading for s in existing_draft.sections]
                existing_draft_summary = (
                    f"\nExisting draft title: {existing_draft.title}\n"
                    f"Sections: {', '.join(section_titles)}"
                )

            system_prompt += DRAFT_REVISION_ADDENDUM.format(
                existing_draft_summary=existing_draft_summary,
                user_query=user_query,
                conversation_context=conversation_context,
            )

        if is_retry:
            reflection = state.get("reflection")
            if reflection and reflection.entries:
                instructions = []
                for entry in reflection.entries:
                    instructions.append(f"- [{entry.error_category.value}] {entry.fix_strategy}")
                system_prompt += DRAFT_REFLECTION_RETRY_ADDENDUM.format(
                    reflection_instructions="\n".join(instructions),
                    num_papers=num_papers,
                )
            else:
                top_errors = qa_errors[:3]
                error_list = "\n".join(f"- {e}" for e in top_errors)
                system_prompt += DRAFT_RETRY_ADDENDUM.format(
                    error_count=len(qa_errors),
                    error_list=error_list,
                    num_papers=num_papers,
                )

        draft = await structured_completion(
            messages=[
                {"role": "system", "content": system_prompt},
                {
                    "role": "user",
                    "content": DRAFT_USER_PROMPT.format(
                        user_query=user_query,
                        paper_context=paper_context,
                    ),
                },
            ],
            response_model=DraftOutput,
            max_tokens=get_draft_max_tokens(num_papers),
        )
        outline = None
    else:
        logger.info(
            "writer_agent: generating outline-based review with %d papers in %s",
            num_papers,
            output_language,
        )

        outline = await _generate_outline(user_query, paper_context, language_name)
        logger.info(
            "writer_agent: outline generated - '%s' with %d sections",
            outline.title,
            len(outline.section_titles),
        )

        logger.info(
            "writer_agent: generating %d sections in parallel",
            len(outline.section_titles),
        )
        section_tasks = [
            _generate_section(
                section_title=section_title,
                section_num=i,
                total_sections=len(outline.section_titles),
                outline_titles=outline.section_titles,
                user_query=user_query,
                paper_context=paper_context,
                language_name=language_name,
                num_papers=num_papers,
            )
            for i, section_title in enumerate(outline.section_titles, 1)
        ]
        section_results = await asyncio.gather(*section_tasks, return_exceptions=True)

        sections: list[ReviewSection] = []
        for i, result in enumerate(section_results):
            title = outline.section_titles[i]
            if isinstance(result, BaseException):
                logger.error("writer_agent: section '%s' generation failed: %s", title, result)
                sections.append(
                    ReviewSection(heading=title, content=f"[Generation failed: {result}]")
                )
            else:
                sections.append(result)

        draft = DraftOutput(title=outline.title, sections=sections)

    cite_pattern = re.compile(r"\{cite:(\d+)\}")
    all_cited_indices: set[int] = set()
    for section in draft.sections:
        all_cited_indices.update({int(m) for m in cite_pattern.findall(section.content)})

    out_of_bounds = [idx for idx in all_cited_indices if idx < 1 or idx > num_papers]
    if out_of_bounds:
        logger.warning(
            "writer_agent: Found out-of-bounds citations: %s (valid range: 1-%d)",
            sorted(out_of_bounds),
            num_papers,
        )

    log_msg = (
        f"Draft complete: '{draft.title}' with {len(draft.sections)} sections, "
        f"{len(all_cited_indices)} unique citations"
    )
    if is_retry:
        log_msg += f" (retry {retry_count})"
    logger.info("writer_agent: %s", log_msg)

    return {
        "final_draft": draft,
        "draft_outline": outline,
        "logs": [log_msg],
        "current_agent": "writer",
        "agent_handoffs": ["extractor→writer"] if not is_retry else ["critic→writer"],
    }


async def critic_agent(state: AgentState) -> dict[str, Any]:
    draft = state.get("final_draft")
    if draft is None:
        log_msg = "QA skipped: no draft to evaluate"
        logger.warning("critic_agent: %s", log_msg)
        return {
            "qa_errors": [],
            "logs": [log_msg],
            "current_agent": "critic",
            "agent_handoffs": ["writer→critic"],
        }

    approved = state.get("approved_papers", [])
    num_papers = len(approved)
    valid_indices: set[int] = set(range(1, num_papers + 1))

    errors: list[str] = []
    all_cited_indices: set[int] = set()

    cite_pattern = re.compile(r"\{cite:(\d+)\}")

    for section_idx, section in enumerate(draft.sections):
        cited_in_content = {int(m) for m in cite_pattern.findall(section.content)}
        all_cited_indices.update(cited_in_content)

        for idx in cited_in_content:
            if idx not in valid_indices:
                errors.append(
                    f"Section {section_idx + 1}: Hallucinated citation index "
                    f"{idx} (valid range: 1-{num_papers})"
                )

        if not cited_in_content:
            errors.append(f"Section {section_idx + 1}: No citations found in content")

    missing = valid_indices - all_cited_indices
    for idx in sorted(missing):
        errors.append(f"Missing citation: paper [{idx}] was approved but not cited")

    retry_count = state.get("retry_count", 0)

    if errors:
        retry_count += 1
        log_msg = f"QA failed with {len(errors)} errors (retry {retry_count}/3): {errors[:3]}"
        logger.warning("critic_agent: %s", log_msg)
        return {
            "qa_errors": errors,
            "retry_count": retry_count,
            "logs": [log_msg],
            "current_agent": "critic",
            "agent_handoffs": ["writer→critic"],
        }

    claim_verification = None
    if CLAIM_VERIFICATION_ENABLED and approved:
        logger.info("critic_agent: starting claim-level verification")
        try:
            _, summary = await verify_draft_citations(
                draft, approved, concurrency=CLAIM_VERIFICATION_CONCURRENCY
            )
            claim_verification = summary

            if summary.total_verifications > 0:
                entailment_ratio = summary.entails_count / summary.total_verifications
                logger.info(
                    "critic_agent: claim verification complete - %d/%d entails (%.1f%%)",
                    summary.entails_count,
                    summary.total_verifications,
                    entailment_ratio * 100,
                )

                if entailment_ratio < MIN_ENTAILMENT_RATIO:
                    failed_details = []
                    for v in summary.failed_verifications[:3]:
                        failed_details.append(
                            f"Claim '{v.claim_text[:50]}...' citing [{v.citation_index}] "
                            f"({v.label.value}): {v.rationale[:100]}"
                        )
                    errors.extend(failed_details)
                    retry_count += 1
                    log_msg = (
                        f"QA failed: citation support ratio {entailment_ratio:.1%} "
                        f"< {MIN_ENTAILMENT_RATIO:.0%} threshold"
                    )
                    logger.warning("critic_agent: %s", log_msg)
                    return {
                        "qa_errors": errors,
                        "retry_count": retry_count,
                        "claim_verification": claim_verification,
                        "logs": [log_msg],
                        "current_agent": "critic",
                        "agent_handoffs": ["writer→critic"],
                    }
        except Exception as e:
            logger.warning("critic_agent: claim verification failed, skipping: %s", e)

    log_msg = "QA passed: all citations verified"
    if claim_verification:
        log_msg += (
            f" (semantic: {claim_verification.entails_count}/"
            f"{claim_verification.total_verifications} entails)"
        )
    logger.info("critic_agent: %s", log_msg)
    return {
        "qa_errors": [],
        "retry_count": retry_count,
        "claim_verification": claim_verification,
        "logs": [log_msg],
        "current_agent": "critic",
        "agent_handoffs": ["writer→critic"],
    }


async def reflection_agent(state: AgentState) -> dict[str, Any]:
    qa_errors = state.get("qa_errors", [])
    retry_count = state.get("retry_count", 0)

    if not qa_errors:
        logger.info("reflection_agent: no errors to reflect on, skipping")
        return {
            "reflection": None,
            "logs": ["Reflection skipped: no QA errors"],
            "current_agent": "reflection",
            "agent_handoffs": ["critic→reflection"],
        }

    error_list = "\n".join(f"- {e}" for e in qa_errors)
    num_papers = len(state.get("approved_papers", []))

    logger.info(
        "reflection_agent: analyzing %d QA errors (retry %d)",
        len(qa_errors),
        retry_count,
    )

    reflection = await structured_completion(
        messages=[
            {"role": "system", "content": REFLECTION_SYSTEM},
            {
                "role": "user",
                "content": REFLECTION_USER.format(
                    num_papers=num_papers,
                    retry_count=retry_count,
                    error_list=error_list,
                ),
            },
        ],
        response_model=Reflection,
    )

    writer_fixable = sum(1 for e in reflection.entries if e.fixable_by_writer)
    retriever_needed = sum(1 for e in reflection.entries if not e.fixable_by_writer)

    logs = [
        f"Reflection: {len(reflection.entries)} errors analyzed "
        f"({writer_fixable} writer-fixable, {retriever_needed} need retriever)",
        f"Reflection: retry_target={reflection.retry_target}, "
        f"should_retry={reflection.should_retry}",
        f"Reflection: {reflection.summary[:150]}",
    ]

    logger.info(
        "reflection_agent: %s (target=%s, should_retry=%s)",
        reflection.summary[:100],
        reflection.retry_target,
        reflection.should_retry,
    )

    return {
        "reflection": reflection,
        "logs": logs,
        "current_agent": "reflection",
        "agent_handoffs": ["critic→reflection"],
    }
