import pytest

from backend.evaluation.academic_style import calculate_academic_style
from backend.evaluation.citation_metrics import (
    calculate_citation_precision,
    calculate_citation_recall,
    extract_citation_indices,
)
from backend.evaluation.cost_tracker import (
    get_cost_efficiency_from_tracking,
    parse_cost_from_logs,
    record_llm_usage,
    record_node_timing,
    reset_tracking,
)
from backend.evaluation.runner import _merge_cost_results, run_evaluation
from backend.evaluation.schemas import CostEfficiencyResult
from backend.evaluation.section_completeness import evaluate_section_completeness
from backend.schemas import (
    ClaimVerificationSummary,
    DraftOutput,
    PaperMetadata,
    PaperSource,
    ReviewSection,
)


@pytest.fixture
def sample_draft() -> DraftOutput:
    return DraftOutput(
        title="A Review of Machine Learning",
        sections=[
            ReviewSection(
                heading="1. Introduction",
                content="Machine learning has revolutionized AI {cite:1}. This may suggest new possibilities {cite:2}.",
            ),
            ReviewSection(
                heading="2. Background",
                content="Deep learning was introduced by researchers {cite:1} {cite:3}. It appears to be effective.",
            ),
            ReviewSection(
                heading="3. Methods",
                content="Various methods have been proposed {cite:2}. The approach seems promising.",
            ),
            ReviewSection(
                heading="4. Discussion",
                content="Results indicate significant improvements {cite:3}. Further research is needed {cite:1}.",
            ),
            ReviewSection(
                heading="5. Conclusion",
                content="In conclusion, ML is transformative {cite:1} {cite:2} {cite:3}.",
            ),
        ],
    )


@pytest.fixture
def sample_papers() -> list[PaperMetadata]:
    return [
        PaperMetadata(
            paper_id="p1",
            title="Paper 1",
            authors=["Author A"],
            abstract="Abstract 1",
            url="http://example.com/1",
            source=PaperSource.SEMANTIC_SCHOLAR,
        ),
        PaperMetadata(
            paper_id="p2",
            title="Paper 2",
            authors=["Author B"],
            abstract="Abstract 2",
            url="http://example.com/2",
            source=PaperSource.ARXIV,
        ),
        PaperMetadata(
            paper_id="p3",
            title="Paper 3",
            authors=["Author C"],
            abstract="Abstract 3",
            url="http://example.com/3",
            source=PaperSource.PUBMED,
        ),
    ]


class TestCitationMetrics:
    def test_extract_citation_indices(self):
        text = "This is a test {cite:1} with multiple {cite:3} citations {cite:2}."
        indices = extract_citation_indices(text)
        assert indices == [1, 3, 2]

    def test_extract_citation_indices_empty(self):
        text = "No citations here."
        indices = extract_citation_indices(text)
        assert indices == []

    def test_citation_precision_all_valid(self, sample_draft: DraftOutput):
        result = calculate_citation_precision(sample_draft, num_approved=3)
        assert result.precision == 1.0
        assert result.invalid_indices == []
        assert result.total_citations > 0

    def test_citation_precision_with_invalid(self):
        draft = DraftOutput(
            title="Test",
            sections=[
                ReviewSection(
                    heading="Test",
                    content="Valid {cite:1} and invalid {cite:5} {cite:10}.",
                )
            ],
        )
        result = calculate_citation_precision(draft, num_approved=3)
        assert result.total_citations == 3
        assert result.valid_citations == 1
        assert result.precision == pytest.approx(1 / 3)
        assert sorted(result.invalid_indices) == [5, 10]

    def test_citation_precision_empty_draft(self):
        draft = DraftOutput(title="Empty", sections=[])
        result = calculate_citation_precision(draft, num_approved=3)
        assert result.precision == 1.0
        assert result.total_citations == 0

    def test_citation_recall_all_cited(
        self, sample_draft: DraftOutput, sample_papers: list[PaperMetadata]
    ):
        result = calculate_citation_recall(sample_draft, sample_papers)
        assert result.recall == 1.0
        assert result.uncited_indices == []

    def test_citation_recall_some_uncited(self, sample_papers: list[PaperMetadata]):
        draft = DraftOutput(
            title="Test",
            sections=[ReviewSection(heading="Test", content="Only citing {cite:1}.")],
        )
        result = calculate_citation_recall(draft, sample_papers)
        assert result.total_approved == 3
        assert result.cited_count == 1
        assert result.recall == pytest.approx(1 / 3)
        assert result.uncited_indices == [2, 3]

    def test_citation_recall_empty_papers(self):
        draft = DraftOutput(
            title="Test",
            sections=[ReviewSection(heading="Test", content="Some text.")],
        )
        result = calculate_citation_recall(draft, [])
        assert result.recall == 1.0


class TestSectionCompleteness:
    def test_all_sections_present(self, sample_draft: DraftOutput):
        result = evaluate_section_completeness(sample_draft, language="en")
        assert result.completeness_score == 1.0
        assert result.missing_sections == []

    def test_missing_sections(self):
        draft = DraftOutput(
            title="Incomplete",
            sections=[
                ReviewSection(heading="Introduction", content="Intro text."),
                ReviewSection(heading="Conclusion", content="Conclusion text."),
            ],
        )
        result = evaluate_section_completeness(draft, language="en")
        assert result.completeness_score < 1.0
        assert len(result.missing_sections) > 0

    def test_alias_matching(self):
        draft = DraftOutput(
            title="With Aliases",
            sections=[
                ReviewSection(heading="Overview", content="Intro."),
                ReviewSection(heading="Related Work", content="Background."),
                ReviewSection(heading="Methodology", content="Methods."),
                ReviewSection(heading="Analysis", content="Discussion."),
                ReviewSection(heading="Summary", content="Conclusion."),
            ],
        )
        result = evaluate_section_completeness(draft, language="en")
        assert result.completeness_score == 1.0

    def test_chinese_sections(self):
        draft = DraftOutput(
            title="中文综述",
            sections=[
                ReviewSection(heading="引言", content="介绍。"),
                ReviewSection(heading="背景", content="背景信息。"),
                ReviewSection(heading="方法", content="方法论。"),
                ReviewSection(heading="讨论", content="讨论内容。"),
                ReviewSection(heading="结论", content="总结。"),
            ],
        )
        result = evaluate_section_completeness(draft, language="zh")
        assert result.completeness_score == 1.0


class TestAcademicStyle:
    def test_hedging_detection(self, sample_draft: DraftOutput):
        result = calculate_academic_style(sample_draft, language="en")
        assert result.hedging_count > 0
        assert result.hedging_ratio > 0

    def test_passive_detection(self):
        draft = DraftOutput(
            title="Passive Test",
            sections=[
                ReviewSection(
                    heading="Test",
                    content="The model was trained. Results were obtained. Data is analyzed.",
                )
            ],
        )
        result = calculate_academic_style(draft, language="en")
        assert result.passive_count > 0

    def test_citation_density(self, sample_draft: DraftOutput):
        result = calculate_academic_style(sample_draft, language="en")
        assert result.citation_count > 0
        assert result.citation_density > 0

    def test_empty_draft(self):
        draft = DraftOutput(title="Empty", sections=[])
        result = calculate_academic_style(draft, language="en")
        assert result.total_sentences == 0
        assert result.hedging_ratio == 0.0


class TestCostTracker:
    def setup_method(self):
        reset_tracking()

    def test_record_and_retrieve_usage(self):
        record_llm_usage(prompt_tokens=100, completion_tokens=50, model="gpt-4o", node="planner")
        record_llm_usage(prompt_tokens=200, completion_tokens=100, model="gpt-4o", node="writer")

        result = get_cost_efficiency_from_tracking()
        assert result.prompt_tokens == 300
        assert result.completion_tokens == 150
        assert result.total_tokens == 450
        assert result.total_llm_calls == 2

    def test_record_node_timing(self):
        record_node_timing("planner", 1000.0)
        record_node_timing("writer", 2000.0)

        result = get_cost_efficiency_from_tracking()
        assert result.node_timings["planner"] == 1000.0
        assert result.node_timings["writer"] == 2000.0
        assert result.total_latency_ms == 3000.0

    def test_parse_logs(self):
        logs = [
            "[planner_agent] completed in 1.5s",
            "[retriever_agent] completed in 8.2s",
            "[writer_agent] completed in 3.0s",
            "Some other log message",
        ]
        result = parse_cost_from_logs(logs)
        assert result.node_timings["planner_agent"] == pytest.approx(1500.0)
        assert result.node_timings["retriever_agent"] == pytest.approx(8200.0)
        assert result.node_timings["writer_agent"] == pytest.approx(3000.0)

    def test_reset_tracking(self):
        record_llm_usage(prompt_tokens=100, completion_tokens=50)
        reset_tracking()
        result = get_cost_efficiency_from_tracking()
        assert result.total_tokens == 0


class TestEvaluationRunner:
    def test_full_evaluation(self, sample_draft: DraftOutput, sample_papers: list[PaperMetadata]):
        logs = ["[planner_agent] completed in 1.0s", "[writer_agent] completed in 2.0s"]
        claim_verification = ClaimVerificationSummary(
            total_claims=10,
            total_verifications=10,
            entails_count=8,
            insufficient_count=2,
            contradicts_count=0,
        )

        result = run_evaluation(
            thread_id="test-thread",
            draft=sample_draft,
            approved_papers=sample_papers,
            logs=logs,
            language="en",
            claim_verification=claim_verification,
        )

        assert result.thread_id == "test-thread"
        assert result.citation_precision.precision == 1.0
        assert result.citation_recall.recall == 1.0
        assert result.claim_support_rate == 0.8
        assert result.section_completeness.completeness_score == 1.0
        assert result.academic_style.total_sentences > 0
        assert result.paper_count == 3
        assert result.automated_score > 0

    def test_evaluation_without_claim_verification(
        self, sample_draft: DraftOutput, sample_papers: list[PaperMetadata]
    ):
        result = run_evaluation(
            thread_id="test-thread",
            draft=sample_draft,
            approved_papers=sample_papers,
            logs=[],
            language="en",
            claim_verification=None,
        )

        assert result.claim_support_rate == 0.0


class TestCostMerge:
    def test_merge_prefers_tracked_tokens(self):
        log_based = CostEfficiencyResult(
            prompt_tokens=0,
            completion_tokens=0,
            total_llm_calls=0,
            total_search_calls=0,
            total_latency_ms=1000.0,
            node_timings={"planner_agent": 1000.0},
        )
        tracked = CostEfficiencyResult(
            prompt_tokens=500,
            completion_tokens=200,
            total_llm_calls=3,
            total_search_calls=0,
            total_latency_ms=2000.0,
            node_timings={"planner_agent": 1500.0, "writer_agent": 500.0},
        )
        merged = _merge_cost_results(log_based, tracked)
        assert merged.prompt_tokens == 500
        assert merged.completion_tokens == 200
        assert merged.total_llm_calls == 3
        assert merged.node_timings["planner_agent"] == 1500.0
        assert merged.node_timings["writer_agent"] == 500.0
        assert merged.total_latency_ms == 2000.0

    def test_merge_falls_back_to_log_when_tracked_empty(self):
        log_based = CostEfficiencyResult(
            prompt_tokens=100,
            completion_tokens=50,
            total_llm_calls=2,
            total_search_calls=1,
            total_latency_ms=3000.0,
            node_timings={"planner_agent": 3000.0},
        )
        tracked = CostEfficiencyResult(
            prompt_tokens=0,
            completion_tokens=0,
            total_llm_calls=0,
            total_search_calls=0,
            total_latency_ms=0,
            node_timings={},
        )
        merged = _merge_cost_results(log_based, tracked)
        assert merged.prompt_tokens == 100
        assert merged.completion_tokens == 50
        assert merged.total_llm_calls == 2
        assert merged.node_timings["planner_agent"] == 3000.0

    def test_evaluation_runner_uses_merged_cost(
        self, sample_draft: DraftOutput, sample_papers: list[PaperMetadata]
    ):
        reset_tracking()
        record_llm_usage(prompt_tokens=300, completion_tokens=150, model="gpt-4o")
        record_node_timing("planner_agent", 1200.0)

        logs = ["[writer_agent] completed in 2.0s"]
        result = run_evaluation(
            thread_id="test-merge",
            draft=sample_draft,
            approved_papers=sample_papers,
            logs=logs,
            language="en",
        )

        assert result.cost_efficiency.prompt_tokens == 300
        assert result.cost_efficiency.completion_tokens == 150
        assert result.cost_efficiency.total_llm_calls == 1
        assert result.cost_efficiency.node_timings["planner_agent"] == 1200.0
        assert result.cost_efficiency.node_timings["writer_agent"] == pytest.approx(2000.0)
        reset_tracking()
