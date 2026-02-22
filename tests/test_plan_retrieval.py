from unittest.mock import AsyncMock, patch

import pytest

from backend.schemas import PaperMetadata, PaperSource, ResearchPlan, SubQuestion
from backend.utils.scholar_api import search_by_plan


def _make_paper(paper_id: str, source: PaperSource) -> PaperMetadata:
    return PaperMetadata(
        paper_id=paper_id,
        title=f"Paper {paper_id}",
        authors=["Author"],
        abstract="Abstract",
        url="http://example.com",
        source=source,
    )


def _make_plan(sub_questions: list[SubQuestion]) -> ResearchPlan:
    return ResearchPlan(
        reasoning="test reasoning",
        sub_questions=sub_questions,
        total_estimated_papers=sum(sq.estimated_papers for sq in sub_questions),
    )


class TestSearchByPlan:
    async def test_empty_sub_questions_returns_empty(self):
        plan = _make_plan([])
        result = await search_by_plan(plan)
        assert result == []

    async def test_single_sub_question_semantic_scholar(self):
        sq = SubQuestion(
            question="What is transformer?",
            keywords=["transformer", "attention"],
            preferred_source=PaperSource.SEMANTIC_SCHOLAR,
            estimated_papers=5,
        )
        plan = _make_plan([sq])
        mock_papers = [_make_paper("ss:1", PaperSource.SEMANTIC_SCHOLAR)]

        with patch(
            "backend.utils.scholar_api.search_semantic_scholar",
            new=AsyncMock(return_value=mock_papers),
        ) as mock_ss:
            result = await search_by_plan(plan)

            mock_ss.assert_called_once_with(["transformer", "attention"], limit_per_query=5)
            assert len(result) == 1
            assert result[0].paper_id == "ss:1"

    async def test_multiple_sub_questions_different_sources(self):
        sqs = [
            SubQuestion(
                question="Deep learning methods",
                keywords=["deep learning", "neural nets"],
                preferred_source=PaperSource.SEMANTIC_SCHOLAR,
                estimated_papers=5,
            ),
            SubQuestion(
                question="Recent arxiv papers",
                keywords=["neural networks", "transformers"],
                preferred_source=PaperSource.ARXIV,
                estimated_papers=8,
            ),
            SubQuestion(
                question="Clinical trials",
                keywords=["clinical ML", "oncology"],
                preferred_source=PaperSource.PUBMED,
                estimated_papers=3,
            ),
        ]
        plan = _make_plan(sqs)

        ss_papers = [_make_paper("ss:1", PaperSource.SEMANTIC_SCHOLAR)]
        arxiv_papers = [_make_paper("arxiv:1", PaperSource.ARXIV)]
        pubmed_papers = [_make_paper("pubmed:1", PaperSource.PUBMED)]

        with (
            patch(
                "backend.utils.scholar_api.search_semantic_scholar",
                new=AsyncMock(return_value=ss_papers),
            ) as mock_ss,
            patch(
                "backend.utils.scholar_api.search_arxiv",
                new=AsyncMock(return_value=arxiv_papers),
            ) as mock_arxiv,
            patch(
                "backend.utils.scholar_api.search_pubmed",
                new=AsyncMock(return_value=pubmed_papers),
            ) as mock_pubmed,
        ):
            result = await search_by_plan(plan)

            mock_ss.assert_called_once_with(["deep learning", "neural nets"], limit_per_query=5)
            mock_arxiv.assert_called_once_with(
                ["neural networks", "transformers"], limit_per_query=8
            )
            mock_pubmed.assert_called_once_with(["clinical ML", "oncology"], limit_per_query=3)
            assert len(result) == 3
            sources = {p.source for p in result}
            assert sources == {
                PaperSource.SEMANTIC_SCHOLAR,
                PaperSource.ARXIV,
                PaperSource.PUBMED,
            }

    async def test_deduplicates_across_sub_questions(self):
        sqs = [
            SubQuestion(
                question="Q1",
                keywords=["transformer", "self-attention"],
                preferred_source=PaperSource.SEMANTIC_SCHOLAR,
                estimated_papers=5,
            ),
            SubQuestion(
                question="Q2",
                keywords=["attention", "mechanism"],
                preferred_source=PaperSource.SEMANTIC_SCHOLAR,
                estimated_papers=5,
            ),
        ]
        plan = _make_plan(sqs)

        shared_paper = _make_paper("ss:dup", PaperSource.SEMANTIC_SCHOLAR)

        with patch(
            "backend.utils.scholar_api.search_semantic_scholar",
            new=AsyncMock(return_value=[shared_paper]),
        ):
            result = await search_by_plan(plan)
            assert len(result) == 1

    async def test_skips_source_with_recent_failures(self):
        sq = SubQuestion(
            question="Q1",
            keywords=["test", "query"],
            preferred_source=PaperSource.ARXIV,
            estimated_papers=5,
        )
        plan = _make_plan([sq])

        with (
            patch("backend.utils.scholar_api.should_skip", return_value=True),
            patch(
                "backend.utils.scholar_api.search_arxiv",
                new=AsyncMock(return_value=[]),
            ) as mock_arxiv,
        ):
            result = await search_by_plan(plan)
            mock_arxiv.assert_not_called()
            assert result == []

    async def test_handles_search_failure_gracefully(self):
        sqs = [
            SubQuestion(
                question="Q1",
                keywords=["test", "query"],
                preferred_source=PaperSource.SEMANTIC_SCHOLAR,
                estimated_papers=5,
            ),
            SubQuestion(
                question="Q2",
                keywords=["test2", "query2"],
                preferred_source=PaperSource.ARXIV,
                estimated_papers=5,
            ),
        ]
        plan = _make_plan(sqs)

        good_paper = _make_paper("arxiv:1", PaperSource.ARXIV)

        with (
            patch(
                "backend.utils.scholar_api.search_semantic_scholar",
                new=AsyncMock(side_effect=Exception("API down")),
            ),
            patch(
                "backend.utils.scholar_api.search_arxiv",
                new=AsyncMock(return_value=[good_paper]),
            ),
        ):
            result = await search_by_plan(plan)
            assert len(result) == 1
            assert result[0].paper_id == "arxiv:1"

    async def test_uses_default_limit_when_estimated_papers_zero(self):
        sq = SubQuestion(
            question="Q1",
            keywords=["test", "query"],
            preferred_source=PaperSource.SEMANTIC_SCHOLAR,
            estimated_papers=5,
        )
        plan = _make_plan([sq])

        with patch(
            "backend.utils.scholar_api.search_semantic_scholar",
            new=AsyncMock(return_value=[]),
        ) as mock_ss:
            await search_by_plan(plan, default_limit=15)
            mock_ss.assert_called_once_with(["test", "query"], limit_per_query=5)


class TestRetrieverAgentPlanBranching:
    async def test_uses_plan_when_available(self):
        from backend.nodes import retriever_agent

        plan = _make_plan(
            [
                SubQuestion(
                    question="Q1",
                    keywords=["kw1", "kw2"],
                    preferred_source=PaperSource.SEMANTIC_SCHOLAR,
                    estimated_papers=5,
                ),
            ]
        )
        mock_papers = [_make_paper("ss:1", PaperSource.SEMANTIC_SCHOLAR)]

        state = {
            "search_keywords": ["kw1"],
            "search_sources": [PaperSource.SEMANTIC_SCHOLAR],
            "research_plan": plan,
        }

        with patch(
            "backend.nodes.search_by_plan",
            new=AsyncMock(return_value=mock_papers),
        ) as mock_sbp:
            result = await retriever_agent(state)

            mock_sbp.assert_called_once()
            assert len(result["candidate_papers"]) == 1
            assert "sub-questions" in result["logs"][0]

    async def test_falls_back_when_no_plan(self):
        from backend.nodes import retriever_agent

        mock_papers = [_make_paper("ss:1", PaperSource.SEMANTIC_SCHOLAR)]

        state = {
            "search_keywords": ["kw1"],
            "search_sources": [PaperSource.SEMANTIC_SCHOLAR],
            "research_plan": None,
        }

        with patch(
            "backend.nodes.search_papers_multi_source",
            new=AsyncMock(return_value=mock_papers),
        ) as mock_sms:
            result = await retriever_agent(state)

            mock_sms.assert_called_once()
            assert len(result["candidate_papers"]) == 1
            assert "queries" in result["logs"][0]

    async def test_falls_back_when_plan_has_no_sub_questions(self):
        from backend.nodes import retriever_agent

        plan = _make_plan([])
        mock_papers = [_make_paper("ss:1", PaperSource.SEMANTIC_SCHOLAR)]

        state = {
            "search_keywords": ["kw1"],
            "search_sources": [PaperSource.SEMANTIC_SCHOLAR],
            "research_plan": plan,
        }

        with patch(
            "backend.nodes.search_papers_multi_source",
            new=AsyncMock(return_value=mock_papers),
        ) as mock_sms:
            result = await retriever_agent(state)

            mock_sms.assert_called_once()
            assert len(result["candidate_papers"]) == 1

    async def test_no_keywords_returns_empty(self):
        from backend.nodes import retriever_agent

        state = {
            "search_keywords": [],
            "search_sources": [PaperSource.SEMANTIC_SCHOLAR],
            "research_plan": None,
        }

        result = await retriever_agent(state)
        assert result["candidate_papers"] == []
        assert "No search keywords" in result["logs"][0]
