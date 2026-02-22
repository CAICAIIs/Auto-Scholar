from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from backend.schemas import PaperMetadata, PaperSource
from backend.utils.scholar_api import (
    _parse_arxiv_papers,
    _parse_pubmed_papers,
    deduplicate_papers,
    search_arxiv,
    search_papers_multi_source,
    search_pubmed,
)

SAMPLE_ARXIV_XML = """<?xml version="1.0" encoding="UTF-8"?>
<feed xmlns="http://www.w3.org/2005/Atom">
  <entry>
    <id>http://arxiv.org/abs/2301.00001v1</id>
    <title>Test Paper on Deep Learning</title>
    <summary>This is a test abstract about deep learning methods.</summary>
    <author><name>John Doe</name></author>
    <author><name>Jane Smith</name></author>
    <published>2023-01-15T00:00:00Z</published>
  </entry>
  <entry>
    <id>http://arxiv.org/abs/2301.00002v1</id>
    <title>Another Test Paper</title>
    <summary>Another abstract for testing.</summary>
    <author><name>Alice Brown</name></author>
    <published>2023-02-20T00:00:00Z</published>
  </entry>
</feed>"""


SAMPLE_PUBMED_ESEARCH = {"esearchresult": {"idlist": ["12345678", "87654321"]}}


SAMPLE_PUBMED_ESUMMARY = {
    "result": {
        "12345678": {
            "title": "PubMed Test Paper One",
            "authors": [{"name": "Smith J"}, {"name": "Doe A"}],
            "pubdate": "2023 Jan",
        },
        "87654321": {
            "title": "PubMed Test Paper Two",
            "authors": [{"name": "Brown B"}],
            "pubdate": "2024 Mar",
        },
    }
}


class TestArxivParsing:
    def test_parse_arxiv_papers_valid_xml(self):
        papers = _parse_arxiv_papers(SAMPLE_ARXIV_XML)

        assert len(papers) == 2

        assert papers[0].paper_id == "arxiv:2301.00001v1"
        assert papers[0].title == "Test Paper on Deep Learning"
        assert "deep learning" in papers[0].abstract.lower()
        assert papers[0].authors == ["John Doe", "Jane Smith"]
        assert papers[0].year == 2023
        assert papers[0].source == PaperSource.ARXIV

        assert papers[1].paper_id == "arxiv:2301.00002v1"
        assert papers[1].authors == ["Alice Brown"]

    def test_parse_arxiv_papers_empty_feed(self):
        empty_xml = """<?xml version="1.0" encoding="UTF-8"?>
        <feed xmlns="http://www.w3.org/2005/Atom"></feed>"""
        papers = _parse_arxiv_papers(empty_xml)
        assert papers == []


class TestPubMedParsing:
    def test_parse_pubmed_papers_valid_data(self):
        papers = _parse_pubmed_papers(SAMPLE_PUBMED_ESUMMARY, ["12345678", "87654321"])

        assert len(papers) == 2

        assert papers[0].paper_id == "pubmed:12345678"
        assert papers[0].title == "PubMed Test Paper One"
        assert papers[0].authors == ["Smith J", "Doe A"]
        assert papers[0].year == 2023
        assert papers[0].source == PaperSource.PUBMED
        assert "pubmed.ncbi.nlm.nih.gov/12345678" in papers[0].url

    def test_parse_pubmed_papers_empty_data(self):
        papers = _parse_pubmed_papers({"result": {}}, [])
        assert papers == []

    def test_parse_pubmed_papers_missing_pmid(self):
        papers = _parse_pubmed_papers(SAMPLE_PUBMED_ESUMMARY, ["99999999"])
        assert papers == []


class TestDeduplication:
    def test_deduplicate_by_paper_id(self):
        papers = [
            PaperMetadata(
                paper_id="paper1",
                title="Test Paper",
                authors=["Author A"],
                abstract="Abstract",
                url="http://example.com",
                source=PaperSource.SEMANTIC_SCHOLAR,
            ),
            PaperMetadata(
                paper_id="paper1",
                title="Test Paper Duplicate",
                authors=["Author B"],
                abstract="Different abstract",
                url="http://example2.com",
                source=PaperSource.ARXIV,
            ),
        ]

        result = deduplicate_papers(papers)
        assert len(result) == 1
        assert result[0].paper_id == "paper1"

    def test_deduplicate_by_title_similarity(self):
        papers = [
            PaperMetadata(
                paper_id="arxiv:123",
                title="Deep Learning for Image Classification",
                authors=["Author A"],
                abstract="Abstract 1",
                url="http://arxiv.org/123",
                source=PaperSource.ARXIV,
            ),
            PaperMetadata(
                paper_id="ss:456",
                title="Deep Learning for Image Classification",
                authors=["Author A"],
                abstract="Abstract 2",
                url="http://semanticscholar.org/456",
                source=PaperSource.SEMANTIC_SCHOLAR,
            ),
        ]

        result = deduplicate_papers(papers)
        assert len(result) == 1
        assert result[0].source == PaperSource.SEMANTIC_SCHOLAR

    def test_deduplicate_preserves_unique_papers(self):
        papers = [
            PaperMetadata(
                paper_id="paper1",
                title="First Unique Paper",
                authors=["Author A"],
                abstract="Abstract 1",
                url="http://example1.com",
                source=PaperSource.SEMANTIC_SCHOLAR,
            ),
            PaperMetadata(
                paper_id="paper2",
                title="Second Unique Paper",
                authors=["Author B"],
                abstract="Abstract 2",
                url="http://example2.com",
                source=PaperSource.ARXIV,
            ),
            PaperMetadata(
                paper_id="paper3",
                title="Third Unique Paper",
                authors=["Author C"],
                abstract="Abstract 3",
                url="http://example3.com",
                source=PaperSource.PUBMED,
            ),
        ]

        result = deduplicate_papers(papers)
        assert len(result) == 3

    def test_deduplicate_empty_list(self):
        result = deduplicate_papers([])
        assert result == []


class TestSearchArxiv:
    @pytest.mark.asyncio
    async def test_search_arxiv_success(self):
        mock_response = AsyncMock()
        mock_response.status = 200
        mock_response.text = AsyncMock(return_value=SAMPLE_ARXIV_XML)
        mock_response.__aenter__ = AsyncMock(return_value=mock_response)
        mock_response.__aexit__ = AsyncMock(return_value=None)

        mock_session = MagicMock()
        mock_session.get = MagicMock(return_value=mock_response)

        with patch("backend.utils.scholar_api.get_session", return_value=mock_session):
            papers = await search_arxiv(["deep learning"], limit_per_query=10)

            assert len(papers) == 2
            assert all(p.source == PaperSource.ARXIV for p in papers)


class TestSearchPubMed:
    @pytest.mark.asyncio
    async def test_search_pubmed_success(self):
        mock_esearch_response = AsyncMock()
        mock_esearch_response.status = 200
        mock_esearch_response.json = AsyncMock(return_value=SAMPLE_PUBMED_ESEARCH)
        mock_esearch_response.__aenter__ = AsyncMock(return_value=mock_esearch_response)
        mock_esearch_response.__aexit__ = AsyncMock(return_value=None)

        mock_esummary_response = AsyncMock()
        mock_esummary_response.status = 200
        mock_esummary_response.json = AsyncMock(return_value=SAMPLE_PUBMED_ESUMMARY)
        mock_esummary_response.__aenter__ = AsyncMock(return_value=mock_esummary_response)
        mock_esummary_response.__aexit__ = AsyncMock(return_value=None)

        mock_session = MagicMock()
        mock_session.get = MagicMock(side_effect=[mock_esearch_response, mock_esummary_response])

        with patch("backend.utils.scholar_api.get_session", return_value=mock_session):
            papers = await search_pubmed(["cancer treatment"], limit_per_query=10)

            assert len(papers) == 2
            assert all(p.source == PaperSource.PUBMED for p in papers)


class TestMultiSourceSearch:
    @pytest.mark.asyncio
    async def test_multi_source_combines_results(self):
        arxiv_papers = [
            PaperMetadata(
                paper_id="arxiv:001",
                title="arXiv Paper",
                authors=["A"],
                abstract="",
                url="",
                source=PaperSource.ARXIV,
            )
        ]
        pubmed_papers = [
            PaperMetadata(
                paper_id="pubmed:001",
                title="PubMed Paper",
                authors=["B"],
                abstract="",
                url="",
                source=PaperSource.PUBMED,
            )
        ]
        ss_papers = [
            PaperMetadata(
                paper_id="ss:001",
                title="Semantic Scholar Paper",
                authors=["C"],
                abstract="",
                url="",
                source=PaperSource.SEMANTIC_SCHOLAR,
            )
        ]

        with patch("backend.utils.scholar_api.search_arxiv", return_value=arxiv_papers):
            with patch("backend.utils.scholar_api.search_pubmed", return_value=pubmed_papers):
                with patch(
                    "backend.utils.scholar_api.search_semantic_scholar", return_value=ss_papers
                ):
                    papers = await search_papers_multi_source(
                        ["test query"],
                        sources=[
                            PaperSource.SEMANTIC_SCHOLAR,
                            PaperSource.ARXIV,
                            PaperSource.PUBMED,
                        ],
                    )

                    assert len(papers) == 3
                    sources_found = {p.source for p in papers}
                    assert PaperSource.ARXIV in sources_found
                    assert PaperSource.PUBMED in sources_found
                    assert PaperSource.SEMANTIC_SCHOLAR in sources_found

    @pytest.mark.asyncio
    async def test_multi_source_single_source(self):
        ss_papers = [
            PaperMetadata(
                paper_id="ss:001",
                title="Paper",
                authors=["A"],
                abstract="",
                url="",
                source=PaperSource.SEMANTIC_SCHOLAR,
            )
        ]

        with patch("backend.utils.scholar_api.search_semantic_scholar", return_value=ss_papers):
            papers = await search_papers_multi_source(
                ["test"],
                sources=[PaperSource.SEMANTIC_SCHOLAR],
            )

            assert len(papers) == 1
            assert papers[0].source == PaperSource.SEMANTIC_SCHOLAR

    @pytest.mark.asyncio
    async def test_multi_source_deduplicates(self):
        arxiv_paper = PaperMetadata(
            paper_id="arxiv:001",
            title="Same Paper Title",
            authors=["A"],
            abstract="",
            url="",
            source=PaperSource.ARXIV,
        )
        ss_paper = PaperMetadata(
            paper_id="ss:001",
            title="Same Paper Title",
            authors=["A"],
            abstract="",
            url="",
            source=PaperSource.SEMANTIC_SCHOLAR,
        )

        with patch("backend.utils.scholar_api.search_arxiv", return_value=[arxiv_paper]):
            with patch(
                "backend.utils.scholar_api.search_semantic_scholar", return_value=[ss_paper]
            ):
                papers = await search_papers_multi_source(
                    ["test"],
                    sources=[PaperSource.SEMANTIC_SCHOLAR, PaperSource.ARXIV],
                )

                assert len(papers) == 1
                assert papers[0].source == PaperSource.SEMANTIC_SCHOLAR

    @pytest.mark.asyncio
    async def test_multi_source_empty_sources(self):
        papers = await search_papers_multi_source(["test"], sources=[])
        assert papers == []

    @pytest.mark.asyncio
    async def test_multi_source_default_semantic_scholar(self):
        ss_papers = [
            PaperMetadata(
                paper_id="ss:001",
                title="Paper",
                authors=["A"],
                abstract="",
                url="",
                source=PaperSource.SEMANTIC_SCHOLAR,
            )
        ]

        with patch("backend.utils.scholar_api.search_semantic_scholar", return_value=ss_papers):
            papers = await search_papers_multi_source(["test"])

            assert len(papers) == 1
            assert papers[0].source == PaperSource.SEMANTIC_SCHOLAR
