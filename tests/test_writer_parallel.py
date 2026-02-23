from unittest.mock import AsyncMock, patch

from backend.schemas import (
    DraftOutline,
    DraftOutput,
    PaperMetadata,
    PaperSource,
    ReviewSection,
)


def _make_paper(paper_id: str, with_contribution: bool = True) -> PaperMetadata:
    return PaperMetadata(
        paper_id=paper_id,
        title=f"Paper {paper_id}",
        authors=["Author A"],
        abstract="Test abstract",
        url="http://example.com",
        source=PaperSource.SEMANTIC_SCHOLAR,
        core_contribution="Test contribution" if with_contribution else None,
    )


class TestWriterParallelSections:
    async def test_parallel_sections_all_succeed(self):
        from backend.nodes import writer_agent

        papers = [_make_paper(f"p{i}") for i in range(3)]
        outline = DraftOutline(
            title="Test Review",
            section_titles=["Introduction", "Methods", "Conclusion"],
        )

        mock_sections = [
            ReviewSection(heading=t, content=f"Content for {t} {{cite:1}}")
            for t in outline.section_titles
        ]

        state = {
            "approved_papers": papers,
            "user_query": "test query about transformers",
            "output_language": "en",
            "is_continuation": False,
            "messages": [],
            "qa_errors": [],
            "retry_count": 0,
        }

        with (
            patch("backend.nodes._generate_outline", new=AsyncMock(return_value=outline)),
            patch(
                "backend.nodes._generate_section",
                new=AsyncMock(side_effect=mock_sections),
            ),
        ):
            result = await writer_agent(state)

            draft = result["final_draft"]
            assert draft is not None
            assert len(draft.sections) == 3
            assert draft.title == "Test Review"
            assert result["current_agent"] == "writer"

    async def test_parallel_sections_one_fails_others_succeed(self):
        from backend.nodes import writer_agent

        papers = [_make_paper(f"p{i}") for i in range(3)]
        outline = DraftOutline(
            title="Test Review",
            section_titles=["Introduction", "Methods", "Conclusion"],
        )

        async def mock_section_gen(**kwargs):
            title = kwargs.get("section_title", "")
            if title == "Methods":
                raise RuntimeError("LLM timeout")
            return ReviewSection(heading=title, content=f"Content for {title} {{cite:1}}")

        state = {
            "approved_papers": papers,
            "user_query": "test query about transformers",
            "output_language": "en",
            "is_continuation": False,
            "messages": [],
            "qa_errors": [],
            "retry_count": 0,
        }

        with (
            patch("backend.nodes._generate_outline", new=AsyncMock(return_value=outline)),
            patch("backend.nodes._generate_section", side_effect=mock_section_gen),
        ):
            result = await writer_agent(state)

            draft = result["final_draft"]
            assert draft is not None
            assert len(draft.sections) == 3
            failed_section = next(s for s in draft.sections if s.heading == "Methods")
            assert "[Generation failed:" in failed_section.content
            ok_sections = [s for s in draft.sections if s.heading != "Methods"]
            assert all("[Generation failed:" not in s.content for s in ok_sections)

    async def test_parallel_sections_all_fail_still_returns_draft(self):
        from backend.nodes import writer_agent

        papers = [_make_paper(f"p{i}") for i in range(3)]
        outline = DraftOutline(
            title="Test Review",
            section_titles=["Introduction", "Methods"],
        )

        state = {
            "approved_papers": papers,
            "user_query": "test query about transformers",
            "output_language": "en",
            "is_continuation": False,
            "messages": [],
            "qa_errors": [],
            "retry_count": 0,
        }

        with (
            patch("backend.nodes._generate_outline", new=AsyncMock(return_value=outline)),
            patch(
                "backend.nodes._generate_section",
                new=AsyncMock(side_effect=RuntimeError("All LLM calls failed")),
            ),
        ):
            result = await writer_agent(state)

            draft = result["final_draft"]
            assert draft is not None
            assert len(draft.sections) == 2
            assert all("[Generation failed:" in s.content for s in draft.sections)

    async def test_continuation_uses_single_call_path(self):
        from backend.nodes import writer_agent

        papers = [_make_paper(f"p{i}") for i in range(3)]
        mock_draft = DraftOutput(
            title="Short Review",
            sections=[ReviewSection(heading="Review", content="Short content {cite:1}")],
        )

        state = {
            "approved_papers": papers,
            "user_query": "add more about BERT",
            "output_language": "en",
            "is_continuation": True,
            "messages": [],
            "qa_errors": [],
            "retry_count": 0,
        }

        with (
            patch("backend.nodes.structured_completion", new=AsyncMock(return_value=mock_draft)),
            patch("backend.nodes._generate_outline") as mock_outline,
        ):
            result = await writer_agent(state)

            mock_outline.assert_not_called()
            assert result["final_draft"] is not None
            assert result["final_draft"].title == "Short Review"
