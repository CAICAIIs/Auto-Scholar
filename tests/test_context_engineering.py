import logging

from backend.constants import (
    CONTEXT_MAX_PAPERS,
    CONTEXT_OVERFLOW_WARNING_THRESHOLD,
)
from backend.nodes import (
    _build_paper_context,
    _estimate_paper_tokens,
    _find_best_keyword_match,
    _prioritize_by_sub_questions,
)
from backend.schemas import (
    PaperMetadata,
    PaperSource,
    ResearchPlan,
    StructuredContribution,
    SubQuestion,
)


def _make_paper(
    paper_id: str,
    title: str = "",
    core_contribution: str = "A contribution",
    structured_contribution: StructuredContribution | None = None,
    abstract: str = "Abstract text",
) -> PaperMetadata:
    return PaperMetadata(
        paper_id=paper_id,
        title=title or f"Paper {paper_id}",
        authors=["Author A"],
        abstract=abstract,
        url="http://example.com",
        source=PaperSource.SEMANTIC_SCHOLAR,
        is_approved=True,
        core_contribution=core_contribution,
        structured_contribution=structured_contribution,
    )


def _make_sub_question(
    question: str = "What is X?",
    keywords: list[str] | None = None,
    preferred_source: PaperSource = PaperSource.SEMANTIC_SCHOLAR,
    priority: int = 1,
) -> SubQuestion:
    return SubQuestion(
        question=question,
        keywords=keywords or ["keyword1", "keyword2"],
        preferred_source=preferred_source,
        priority=priority,
    )


def _make_plan(sub_questions: list[SubQuestion]) -> ResearchPlan:
    return ResearchPlan(
        reasoning="test reasoning",
        sub_questions=sub_questions,
        total_estimated_papers=sum(sq.estimated_papers for sq in sub_questions),
    )


class TestEstimatePaperTokens:
    def test_returns_positive_for_minimal_paper(self):
        paper = _make_paper("p1", title="Short", core_contribution="C")
        tokens = _estimate_paper_tokens(paper)
        assert tokens >= 20

    def test_uses_structured_contribution_fields(self):
        sc = StructuredContribution(
            problem="A problem statement with several words",
            method="A method description with several words",
            novelty="Novel approach with many details here",
        )
        paper_with_sc = _make_paper("p1", structured_contribution=sc)
        paper_without_sc = _make_paper("p2")
        assert _estimate_paper_tokens(paper_with_sc) > _estimate_paper_tokens(paper_without_sc)

    def test_falls_back_to_abstract_when_no_structured_contribution(self):
        paper = _make_paper(
            "p1",
            core_contribution="C",
            structured_contribution=None,
            abstract="A long abstract " * 20,
        )
        tokens = _estimate_paper_tokens(paper)
        assert tokens > 20

    def test_minimum_floor_of_20(self):
        paper = _make_paper("p1", title="X", core_contribution="Y", abstract="")
        tokens = _estimate_paper_tokens(paper)
        assert tokens >= 20


class TestFindBestKeywordMatch:
    def test_returns_paper_matching_most_keywords(self):
        papers = [
            _make_paper("p1", title="Transformer Architecture"),
            _make_paper("p2", title="Transformer Attention Mechanism"),
            _make_paper("p3", title="Unrelated Topic"),
        ]
        result = _find_best_keyword_match(papers, ["transformer", "attention"])
        assert result is not None
        assert result.paper_id == "p2"

    def test_returns_first_paper_when_no_keyword_match(self):
        papers = [
            _make_paper("p1", title="Alpha"),
            _make_paper("p2", title="Beta"),
        ]
        result = _find_best_keyword_match(papers, ["gamma", "delta"])
        assert result is not None
        assert result.paper_id == "p1"

    def test_returns_none_for_empty_papers(self):
        assert _find_best_keyword_match([], ["keyword"]) is None

    def test_returns_none_for_empty_keywords(self):
        papers = [_make_paper("p1")]
        assert _find_best_keyword_match(papers, []) is None

    def test_case_insensitive_matching(self):
        papers = [
            _make_paper("p1", title="deep learning survey"),
            _make_paper("p2", title="DEEP LEARNING Applications"),
        ]
        result = _find_best_keyword_match(papers, ["Deep", "Learning", "Applications"])
        assert result is not None
        assert result.paper_id == "p2"


class TestPrioritizeBySubQuestions:
    def test_reserves_one_paper_per_sub_question(self):
        papers = [
            _make_paper("p1", title="Transformer Architecture"),
            _make_paper("p2", title="Medical Imaging Analysis"),
            _make_paper("p3", title="Reinforcement Learning"),
        ]
        plan = _make_plan(
            [
                _make_sub_question(keywords=["transformer", "architecture"], priority=1),
                _make_sub_question(keywords=["medical", "imaging"], priority=2),
            ]
        )
        result = _prioritize_by_sub_questions(papers, plan)
        assert len(result) == 3
        assert result[0].paper_id == "p1"
        assert result[1].paper_id == "p2"

    def test_higher_priority_sub_questions_pick_first(self):
        papers = [
            _make_paper("p1", title="Shared Topic Paper"),
        ]
        plan = _make_plan(
            [
                _make_sub_question(keywords=["shared", "topic"], priority=2),
                _make_sub_question(keywords=["shared", "topic"], priority=1),
            ]
        )
        result = _prioritize_by_sub_questions(papers, plan)
        assert result[0].paper_id == "p1"

    def test_remaining_papers_preserved_after_reserved(self):
        papers = [
            _make_paper("p1", title="Alpha"),
            _make_paper("p2", title="Beta"),
            _make_paper("p3", title="Gamma"),
        ]
        plan = _make_plan(
            [
                _make_sub_question(keywords=["beta", "topic"], priority=1),
            ]
        )
        result = _prioritize_by_sub_questions(papers, plan)
        assert result[0].paper_id == "p2"
        remaining_ids = [p.paper_id for p in result[1:]]
        assert "p1" in remaining_ids
        assert "p3" in remaining_ids

    def test_handles_more_sub_questions_than_papers(self):
        papers = [_make_paper("p1", title="Only Paper")]
        plan = _make_plan(
            [
                _make_sub_question(keywords=["only", "paper"], priority=1),
                _make_sub_question(keywords=["missing", "topic"], priority=2),
                _make_sub_question(keywords=["absent", "topic"], priority=3),
            ]
        )
        result = _prioritize_by_sub_questions(papers, plan)
        assert len(result) == 1
        assert result[0].paper_id == "p1"


class TestBuildPaperContext:
    def test_returns_empty_string_for_no_papers(self):
        assert _build_paper_context([]) == ""

    def test_includes_all_papers_within_budget(self):
        papers = [_make_paper(f"p{i}") for i in range(5)]
        context = _build_paper_context(papers)
        for i in range(1, 6):
            assert f"[{i}]" in context

    def test_truncates_when_budget_exceeded(self):
        papers = [_make_paper(f"p{i}") for i in range(100)]
        context = _build_paper_context(papers, token_budget=500)
        assert "[1]" in context
        assert "[100]" not in context

    def test_respects_max_papers_hard_limit(self, caplog):
        papers = [_make_paper(f"p{i}") for i in range(CONTEXT_MAX_PAPERS + 20)]
        with caplog.at_level(logging.WARNING):
            context = _build_paper_context(papers, token_budget=999999)
        assert f"exceeds hard limit {CONTEXT_MAX_PAPERS}" in caplog.text
        paper_count = context.count("\n\n") + 1 if context else 0
        assert paper_count <= CONTEXT_MAX_PAPERS

    def test_logs_warning_when_exceeding_overflow_threshold(self, caplog):
        count = CONTEXT_OVERFLOW_WARNING_THRESHOLD + 5
        papers = [_make_paper(f"p{i}") for i in range(count)]
        with caplog.at_level(logging.WARNING):
            _build_paper_context(papers, token_budget=999999)
        assert f"exceeds warning threshold {CONTEXT_OVERFLOW_WARNING_THRESHOLD}" in caplog.text

    def test_no_warning_below_threshold(self, caplog):
        papers = [_make_paper(f"p{i}") for i in range(5)]
        with caplog.at_level(logging.WARNING):
            _build_paper_context(papers)
        assert "exceeds warning threshold" not in caplog.text

    def test_applies_sub_question_prioritization(self):
        papers = [
            _make_paper("p1", title="Unrelated Topic"),
            _make_paper("p2", title="Target Keyword Paper"),
        ]
        plan = _make_plan(
            [
                _make_sub_question(keywords=["target", "keyword"], priority=1),
            ]
        )
        context = _build_paper_context(papers, research_plan=plan, token_budget=500)
        first_bracket = context.index("[1]")
        assert "Target Keyword Paper" in context[first_bracket : first_bracket + 100]

    def test_skips_prioritization_without_plan(self):
        papers = [
            _make_paper("p1", title="First"),
            _make_paper("p2", title="Second"),
        ]
        context = _build_paper_context(papers, research_plan=None)
        pos_first = context.index("First")
        pos_second = context.index("Second")
        assert pos_first < pos_second

    def test_budget_allows_at_least_one_paper(self):
        papers = [_make_paper("p1", core_contribution="A very long " * 100)]
        context = _build_paper_context(papers, token_budget=1)
        assert "[1]" in context

    def test_uses_default_budget_from_constants(self):
        papers = [_make_paper(f"p{i}") for i in range(10)]
        context = _build_paper_context(papers)
        assert "[1]" in context
        assert context


class TestBuildPaperContextIntegration:
    def test_budget_logs_info_when_truncating(self, caplog):
        papers = [_make_paper(f"p{i}") for i in range(50)]
        with caplog.at_level(logging.INFO):
            _build_paper_context(papers, token_budget=200)
        assert "context budget reached" in caplog.text

    def test_structured_contribution_included_in_output(self):
        sc = StructuredContribution(problem="The problem", method="The method")
        paper = _make_paper("p1", structured_contribution=sc)
        context = _build_paper_context([paper])
        assert "Problem: The problem" in context
        assert "Method: The method" in context

    def test_abstract_fallback_when_no_structured_contribution(self):
        paper = _make_paper("p1", structured_contribution=None, abstract="My abstract text")
        context = _build_paper_context([paper])
        assert "Abstract: My abstract text" in context
