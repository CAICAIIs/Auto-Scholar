"""Shared test fixtures for mocking external API calls.

This file provides fixtures for mocking Semantic Scholar, arXiv, and PubMed API calls
in integration tests. These fixtures eliminate network dependencies and prevent test timeouts.

Usage:
    async def test_my_feature(mock_external_apis_success):
        # Test code here - external APIs are mocked
        assert ...
"""

import pytest
from unittest.mock import AsyncMock, patch

from app.schemas import PaperMetadata, PaperSource


# Mock paper data matching PaperMetadata schema from app/schemas.py
MOCK_SEMANTIC_PAPERS: list[PaperMetadata] = [
    PaperMetadata(
        paper_id="sem_001",
        source=PaperSource.SEMANTIC_SCHOLAR,
        title="Transformer-Based Literature Synthesis",
        abstract="We evaluate transformer methods for automated literature reviews...",
        authors=["Alice Chen", "Bob Smith"],
        year=2023,
        url="https://www.semanticscholar.org/paper/sem_001",
    ),
    PaperMetadata(
        paper_id="sem_002",
        source=PaperSource.SEMANTIC_SCHOLAR,
        title="Evidence Aggregation in Scientific QA",
        abstract="This work studies citation-grounded scientific question answering...",
        authors=["Dana Li"],
        year=2022,
        url="https://www.semanticscholar.org/paper/sem_002",
    ),
    PaperMetadata(
        paper_id="sem_003",
        source=PaperSource.SEMANTIC_SCHOLAR,
        title="Neural Architecture Search for NLP",
        abstract="Automated design of neural networks for natural language tasks...",
        authors=["Carlos Rodriguez", "Emma Wilson"],
        year=2024,
        url="https://www.semanticscholar.org/paper/sem_003",
    ),
]


MOCK_ARXIV_PAPERS: list[PaperMetadata] = [
    PaperMetadata(
        paper_id="arxiv:2401.01234",
        source=PaperSource.ARXIV,
        title="Multi-Source Retrieval for Research Agents",
        abstract="A retrieval architecture combining curated and open repositories...",
        authors=["Eva Park", "Noah Kim"],
        year=2024,
        url="https://arxiv.org/abs/2401.01234",
    ),
    PaperMetadata(
        paper_id="arxiv:2312.05678",
        source=PaperSource.ARXIV,
        title="Efficient Attention Mechanisms",
        abstract="Reducing computational complexity of attention in transformer models...",
        authors=["Michael Johnson", "Sarah Lee"],
        year=2023,
        url="https://arxiv.org/abs/2312.05678",
    ),
]


MOCK_PUBMED_PAPERS: list[PaperMetadata] = [
    PaperMetadata(
        paper_id="pubmed:39876543",
        source=PaperSource.PUBMED,
        title="Clinical Evidence Summarization with LLMs",
        abstract="We benchmark LLM-assisted synthesis on biomedical abstracts...",
        authors=["M. Rivera", "J. Patel"],
        year=2021,
        url="https://pubmed.ncbi.nlm.nih.gov/39876543/",
    ),
    PaperMetadata(
        paper_id="pubmed:38712345",
        source=PaperSource.PUBMED,
        title="Machine Learning in Oncology",
        abstract="Comprehensive review of ML applications in cancer diagnosis...",
        authors=["L. Chen", "T. Williams"],
        year=2022,
        url="https://pubmed.ncbi.nlm.nih.gov/38712345/",
    ),
]


@pytest.fixture
def mock_paper_data():
    """Fixture providing mock paper data for all sources.

    Returns:
        dict: Maps source names to their mock paper lists
    """
    return {
        "semantic": MOCK_SEMANTIC_PAPERS,
        "arxiv": MOCK_ARXIV_PAPERS,
        "pubmed": MOCK_PUBMED_PAPERS,
    }


@pytest.fixture
def mock_external_apis_success(mock_paper_data):
    """Fixture that patches all external API clients with successful responses.

    This fixture patches:
    - app.utils.scholar_api.search_semantic_scholar
    - app.utils.scholar_api.search_arxiv
    - app.utils.scholar_api.search_pubmed
    - app.utils.scholar_api.search_papers_multi_source

    Yields:
        dict: Mock objects for each source (for asserting call counts)
    """
    with patch(
        "app.utils.scholar_api.search_semantic_scholar",
        new=AsyncMock(return_value=mock_paper_data["semantic"]),
    ) as m_sem, patch(
        "app.utils.scholar_api.search_arxiv",
        new=AsyncMock(return_value=mock_paper_data["arxiv"]),
    ) as m_arx, patch(
        "app.utils.scholar_api.search_pubmed",
        new=AsyncMock(return_value=mock_paper_data["pubmed"]),
    ) as m_pub:
        yield {"semantic": m_sem, "arxiv": m_arx, "pubmed": m_pub}


@pytest.fixture
def mock_external_apis_empty(mock_paper_data):
    """Fixture that patches all external APIs to return empty results.

    Use this to test handling of no papers found scenarios.

    Yields:
        dict: Mock objects for each source (for asserting call counts)
    """
    with patch(
        "app.utils.scholar_api.search_semantic_scholar",
        new=AsyncMock(return_value=[]),
    ) as m_sem, patch(
        "app.utils.scholar_api.search_arxiv",
        new=AsyncMock(return_value=[]),
    ) as m_arx, patch(
        "app.utils.scholar_api.search_pubmed",
        new=AsyncMock(return_value=[]),
    ) as m_pub:
        yield {"semantic": m_sem, "arxiv": m_arx, "pubmed": m_pub}


@pytest.fixture
def mock_external_apis_partial_failure(mock_paper_data):
    """Fixture that patches external APIs with one source returning empty results.

    This simulates a scenario where one source fails or returns no results
    while others succeed.

    Yields:
        dict: Mock objects for each source (for asserting call counts)
    """
    with patch(
        "app.utils.scholar_api.search_semantic_scholar",
        new=AsyncMock(return_value=mock_paper_data["semantic"]),
    ) as m_sem, patch(
        "app.utils.scholar_api.search_arxiv",
        new=AsyncMock(return_value=[]),  # arXiv returns empty
    ) as m_arx, patch(
        "app.utils.scholar_api.search_pubmed",
        new=AsyncMock(return_value=mock_paper_data["pubmed"]),
    ) as m_pub:
        yield {"semantic": m_sem, "arxiv": m_arx, "pubmed": m_pub}
