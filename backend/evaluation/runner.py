from backend.evaluation.academic_style import calculate_academic_style
from backend.evaluation.citation_metrics import (
    calculate_citation_precision,
    calculate_citation_recall,
)
from backend.evaluation.cost_tracker import get_cost_efficiency_from_tracking, parse_cost_from_logs
from backend.evaluation.human_ratings import get_rating_summary
from backend.evaluation.schemas import CostEfficiencyResult, EvaluationResult
from backend.evaluation.section_completeness import evaluate_section_completeness
from backend.schemas import ClaimVerificationSummary, DraftOutput, PaperMetadata


def _merge_cost_results(
    log_based: CostEfficiencyResult,
    tracked: CostEfficiencyResult,
) -> CostEfficiencyResult:
    """Merge log-parsed and runtime-tracked cost data, preferring tracked when available."""
    merged_timings = dict(log_based.node_timings)
    for node, ms in tracked.node_timings.items():
        merged_timings[node] = ms

    return CostEfficiencyResult(
        prompt_tokens=tracked.prompt_tokens
        if tracked.prompt_tokens > 0
        else log_based.prompt_tokens,
        completion_tokens=tracked.completion_tokens
        if tracked.completion_tokens > 0
        else log_based.completion_tokens,
        total_llm_calls=tracked.total_llm_calls
        if tracked.total_llm_calls > 0
        else log_based.total_llm_calls,
        total_search_calls=max(log_based.total_search_calls, tracked.total_search_calls),
        total_latency_ms=sum(merged_timings.values()),
        node_timings=merged_timings,
    )


def run_evaluation(
    thread_id: str,
    draft: DraftOutput,
    approved_papers: list[PaperMetadata],
    logs: list[str],
    language: str = "en",
    claim_verification: ClaimVerificationSummary | None = None,
) -> EvaluationResult:
    num_approved = len(approved_papers)

    citation_precision = calculate_citation_precision(draft, num_approved)
    citation_recall = calculate_citation_recall(draft, approved_papers)
    section_completeness = evaluate_section_completeness(draft, language)
    academic_style = calculate_academic_style(draft, language)

    log_cost = parse_cost_from_logs(logs)
    tracked_cost = get_cost_efficiency_from_tracking()
    cost_efficiency = _merge_cost_results(log_cost, tracked_cost)

    claim_support_rate = 0.0
    if claim_verification and claim_verification.total_verifications > 0:
        claim_support_rate = (
            claim_verification.entails_count / claim_verification.total_verifications
        )

    human_ratings = get_rating_summary(thread_id)

    return EvaluationResult(
        thread_id=thread_id,
        citation_precision=citation_precision,
        citation_recall=citation_recall,
        claim_support_rate=claim_support_rate,
        section_completeness=section_completeness,
        academic_style=academic_style,
        cost_efficiency=cost_efficiency,
        human_ratings=human_ratings,
        language=language,
        paper_count=num_approved,
    )
