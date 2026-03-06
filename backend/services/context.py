import logging

from backend.constants import CONTEXT_MAX_PAPERS, CONTEXT_TOKEN_BUDGET
from backend.schemas import MethodComparisonEntry, PaperMetadata, ResearchPlan

logger = logging.getLogger(__name__)


def estimate_paper_tokens(paper: PaperMetadata) -> int:
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


def prioritize_by_sub_questions(
    papers: list[PaperMetadata],
    research_plan: ResearchPlan,
) -> list[PaperMetadata]:
    reserved: list[PaperMetadata] = []
    remaining = list(papers)

    for sq in sorted(research_plan.sub_questions, key=lambda s: s.priority):
        best = find_best_keyword_match(remaining, sq.keywords)
        if best:
            reserved.append(best)
            remaining.remove(best)

    return reserved + remaining


def find_best_keyword_match(
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


def build_paper_context(
    papers: list[PaperMetadata],
    token_budget: int = CONTEXT_TOKEN_BUDGET,
) -> str:
    if not papers:
        return ""

    if len(papers) > CONTEXT_MAX_PAPERS:
        logger.warning(
            "paper count %d exceeds hard limit %d, truncating (legacy data?)",
            len(papers),
            CONTEXT_MAX_PAPERS,
        )
        papers = papers[:CONTEXT_MAX_PAPERS]

    selected: list[PaperMetadata] = []
    estimated_tokens = 0
    for p in papers:
        paper_tokens = estimate_paper_tokens(p)
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
