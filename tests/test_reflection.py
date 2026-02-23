from unittest.mock import AsyncMock, patch

from backend.schemas import (
    ErrorCategory,
    PaperMetadata,
    PaperSource,
    Reflection,
    ReflectionEntry,
)
from backend.workflow import _qa_router, _reflection_router


def _make_paper(paper_id: str) -> PaperMetadata:
    return PaperMetadata(
        paper_id=paper_id,
        title=f"Paper {paper_id}",
        authors=["Author"],
        abstract="Abstract",
        url="http://example.com",
        source=PaperSource.SEMANTIC_SCHOLAR,
        is_approved=True,
        core_contribution="A contribution",
    )


def _make_reflection(
    should_retry: bool = True,
    retry_target: str = "writer_agent",
    entries: list[ReflectionEntry] | None = None,
) -> Reflection:
    if entries is None:
        entries = [
            ReflectionEntry(
                error_category=ErrorCategory.CITATION_OUT_OF_BOUNDS,
                error_detail="Citation {cite:99} exceeds valid range 1-5",
                fix_strategy="Replace {cite:99} with a valid index 1-5",
                fixable_by_writer=True,
            ),
        ]
    return Reflection(
        entries=entries,
        should_retry=should_retry,
        retry_target=retry_target,
        summary="Test reflection summary",
    )


class TestQaRouter:
    def test_routes_to_end_when_no_errors(self):
        state = {"qa_errors": [], "retry_count": 0}
        assert _qa_router(state) == "__end__"

    def test_routes_to_reflection_when_errors_exist(self):
        state = {"qa_errors": ["Some error"], "retry_count": 0}
        assert _qa_router(state) == "reflection_agent"

    def test_routes_to_reflection_regardless_of_retry_count(self):
        state = {"qa_errors": ["Error"], "retry_count": 5}
        assert _qa_router(state) == "reflection_agent"


class TestReflectionRouter:
    def test_routes_to_end_when_no_reflection(self):
        state = {"reflection": None, "retry_count": 0}
        assert _reflection_router(state) == "__end__"

    def teroutes_to_end_when_should_retry_false(self):
        reflection = _make_reflection(should_retry=False)
        state = {"reflection": reflection, "retry_count": 0}
        assert _reflection_router(state) == "__end__"

    def test_routes_to_end_when_max_retries_reached(self):
        reflection = _make_reflection(should_retry=True, retry_target="writer_agent")
        state = {"reflection": reflection, "retry_count": 3}
        assert _reflection_router(state) == "__end__"

    def test_routes_to_writer_agent(self):
        reflection = _make_reflection(should_retry=True, retry_target="writer_agent")
        state = {"reflection": reflection, "retry_count": 1}
        assert _reflection_router(state) == "writer_agent"

    def test_routes_to_retriever_agent(self):
        reflection = _make_reflection(should_retry=True, retry_target="retriever_agent")
        state = {"reflection": reflection, "retry_count": 1}
        assert _reflection_router(state) == "retriever_agent"

    def test_defaults_to_writer_for_unknown_target(self):
        reflection = _make_reflection(should_retry=True, retry_target="unknown_agent")
        state = {"reflection": reflection, "retry_count": 0}
        assert _reflection_router(state) == "writer_agent"


class TestReflectionAgent:
    async def test_skips_when_no_errors(self):
        from backend.nodes import reflection_agent

        state = {"qa_errors": [], "retry_count": 0, "approved_papers": []}
        result = await reflection_agent(state)

        assert result["reflection"] is None
        assert "skipped" in result["logs"][0].lower()

    async def test_calls_llm_and_returns_reflection(self):
        from backend.nodes import reflection_agent

        mock_reflection = _make_reflection(
            should_retry=True,
            retry_target="writer_agent",
            entries=[
                ReflectionEntry(
                    error_category=ErrorCategory.MISSING_CITATION,
                    error_detail="Section 2 has no citations",
                    fix_strategy="Add at least one {cite:N} to section 2",
                    fixable_by_writer=True,
                ),
            ],
        )

        state = {
            "qa_errors": ["Section 2: No citations found in content"],
            "retry_count": 1,
            "approved_papers": [_make_paper("p1"), _make_paper("p2")],
        }

        with patch(
            "backend.nodes.structured_completion",
            new=AsyncMock(return_value=mock_reflection),
        ) as mock_llm:
            result = await reflection_agent(state)

            mock_llm.assert_called_once()
            assert result["reflection"] is not None
            assert result["reflection"].should_retry is True
            assert result["reflection"].retry_target == "writer_agent"
            assert len(result["reflection"].entries) == 1
            assert result["current_agent"] == "reflection"

    async def test_logs_contain_analysis_summary(self):
        from backend.nodes import reflection_agent

        mock_reflection = _make_reflection(
            entries=[
                ReflectionEntry(
                    error_category=ErrorCategory.CITATION_OUT_OF_BOUNDS,
                    error_detail="cite:99",
                    fix_strategy="Fix index",
                    fixable_by_writer=True,
                ),
                ReflectionEntry(
                    error_category=ErrorCategory.UNCITED_PAPER,
                    error_detail="Paper 3 uncited",
                    fix_strategy="Cite paper 3",
                    fixable_by_writer=True,
                ),
            ],
        )

        state = {
            "qa_errors": ["Error 1", "Error 2"],
            "retry_count": 0,
            "approved_papers": [_make_paper("p1")],
        }

        with patch(
            "backend.nodes.structured_completion",
            new=AsyncMock(return_value=mock_reflection),
        ):
            result = await reflection_agent(state)
            log_text = " ".join(result["logs"])
            assert "2 errors analyzed" in log_text
            assert "2 writer-fixable" in log_text

    async def test_mixed_fixability_logged(self):
        from backend.nodes import reflection_agent

        mock_reflection = _make_reflection(
            retry_target="retriever_agent",
            entries=[
                ReflectionEntry(
                    error_category=ErrorCategory.CITATION_OUT_OF_BOUNDS,
                    error_detail="cite:99",
                    fix_strategy="Fix index",
                    fixable_by_writer=True,
                ),
                ReflectionEntry(
                    error_category=ErrorCategory.LOW_ENTAILMENT,
                    error_detail="Not enough papers",
                    fix_strategy="Search for more papers",
                    fixable_by_writer=False,
                ),
            ],
        )

        state = {
            "qa_errors": ["Error 1", "Error 2"],
            "retry_count": 0,
            "approved_papers": [],
        }

        with patch(
            "backend.nodes.structured_completion",
            new=AsyncMock(return_value=mock_reflection),
        ):
            result = await reflection_agent(state)
            log_text = " ".join(result["logs"])
            assert "1 writer-fixable" in log_text
            assert "1 need retriever" in log_text


class TestWriterUsesReflection:
    async def test_writer_uses_reflection_strategies_on_retry(self):
        from backend.nodes import writer_agent

        reflection = _make_reflection(
            entries=[
                ReflectionEntry(
                    error_category=ErrorCategory.MISSING_CITATION,
                    error_detail="Section 2 has no citations",
                    fix_strategy="Add {cite:1} or {cite:2} to section 2",
                    fixable_by_writer=True,
                ),
            ],
        )

        papers = [_make_paper("p1"), _make_paper("p2")]

        state = {
            "approved_papers": papers,
            "user_query": "test query",
            "output_language": "en",
            "is_continuation": False,
            "messages": [],
            "qa_errors": ["Section 2: No citations"],
            "retry_count": 1,
            "reflection": reflection,
            "final_draft": None,
            "draft_outline": None,
        }

        from backend.schemas import DraftOutput, ReviewSection

        mock_draft = DraftOutput(
            title="Test",
            sections=[
                ReviewSection(heading="Intro", content="Text {cite:1} and {cite:2}"),
            ],
        )

        with patch(
            "backend.nodes.structured_completion",
            new=AsyncMock(return_value=mock_draft),
        ) as mock_llm:
            await writer_agent(state)

            call_args = mock_llm.call_args
            system_msg = call_args.kwargs["messages"][0]["content"]
            assert "reflection agent" in system_msg.lower()
            assert "missing_citation" in system_msg

    async def test_writer_falls_back_to_legacy_retry_without_reflection(self):
        from backend.nodes import writer_agent

        papers = [_make_paper("p1")]

        state = {
            "approved_papers": papers,
            "user_query": "test query",
            "output_language": "en",
            "is_continuation": False,
            "messages": [],
            "qa_errors": ["Section 1: error"],
            "retry_count": 1,
            "reflection": None,
            "final_draft": None,
            "draft_outline": None,
        }

        from backend.schemas import DraftOutput, ReviewSection

        mock_draft = DraftOutput(
            title="Test",
            sections=[
                ReviewSection(heading="Intro", content="Text {cite:1}"),
            ],
        )

        with patch(
            "backend.nodes.structured_completion",
            new=AsyncMock(return_value=mock_draft),
        ) as mock_llm:
            await writer_agent(state)

            call_args = mock_llm.call_args
            system_msg = call_args.kwargs["messages"][0]["content"]
            assert "PREVIOUS ATTEMPT FAILED" in system_msg
            assert "reflection agent" not in system_msg.lower()


class TestReflectionSchemaValidation:
    def test_error_category_values(self):
        assert ErrorCategory.CITATION_OUT_OF_BOUNDS == "citation_out_of_bounds"
        assert ErrorCategory.MISSING_CITATION == "missing_citation"
        assert ErrorCategory.UNCITED_PAPER == "uncited_paper"
        assert ErrorCategory.LOW_ENTAILMENT == "low_entailment"
        assert ErrorCategory.STRUCTURAL == "structural"

    def test_reflection_entry_creation(self):
        entry = ReflectionEntry(
            error_category=ErrorCategory.LOW_ENTAILMENT,
            error_detail="Claim not supported",
            fix_strategy="Rephrase claim to match paper content",
            fixable_by_writer=True,
        )
        assert entry.error_category == ErrorCategory.LOW_ENTAILMENT
        assert entry.fixable_by_writer is True

    def test_reflection_defaults(self):
        reflection = Reflection(
            entries=[],
            should_retry=False,
            summary="No issues",
        )
        assert reflection.retry_target == "writer_agent"
        assert reflection.entries == []

    def test_reflection_with_multiple_entries(self):
        entries = [
            ReflectionEntry(
                error_category=ErrorCategory.CITATION_OUT_OF_BOUNDS,
                error_detail="cite:99",
                fix_strategy="Fix",
                fixable_by_writer=True,
            ),
            ReflectionEntry(
                error_category=ErrorCategory.UNCITED_PAPER,
                error_detail="Paper 3",
                fix_strategy="Cite it",
                fixable_by_writer=True,
            ),
        ]
        reflection = Reflection(
            entries=entries,
            should_retry=True,
            retry_target="writer_agent",
            summary="Two errors found",
        )
        assert len(reflection.entries) == 2
        assert reflection.should_retry is True
