import base64

import pytest

from backend.schemas import PaperMetadata, PaperSource
from backend.utils.charts import (
    generate_all_charts,
    generate_author_frequency_chart,
    generate_source_distribution_chart,
    generate_year_trend_chart,
)


@pytest.fixture
def sample_papers() -> list[PaperMetadata]:
    return [
        PaperMetadata(
            paper_id="p1",
            title="Paper 1",
            authors=["Alice", "Bob"],
            abstract="Abstract 1",
            url="https://example.com/1",
            year=2022,
            source=PaperSource.SEMANTIC_SCHOLAR,
        ),
        PaperMetadata(
            paper_id="p2",
            title="Paper 2",
            authors=["Alice", "Charlie"],
            abstract="Abstract 2",
            url="https://example.com/2",
            year=2023,
            source=PaperSource.ARXIV,
        ),
        PaperMetadata(
            paper_id="p3",
            title="Paper 3",
            authors=["Bob", "David"],
            abstract="Abstract 3",
            url="https://example.com/3",
            year=2023,
            source=PaperSource.SEMANTIC_SCHOLAR,
        ),
        PaperMetadata(
            paper_id="p4",
            title="Paper 4",
            authors=["Alice", "Eve"],
            abstract="Abstract 4",
            url="https://example.com/4",
            year=2024,
            source=PaperSource.PUBMED,
        ),
    ]


def test_generate_year_trend_chart(sample_papers: list[PaperMetadata]):
    result = generate_year_trend_chart(sample_papers)

    assert result is not None
    decoded = base64.b64decode(result)
    assert decoded[:8] == b"\x89PNG\r\n\x1a\n"


def test_generate_year_trend_chart_empty():
    result = generate_year_trend_chart([])
    assert result is None


def test_generate_year_trend_chart_no_years():
    papers = [
        PaperMetadata(
            paper_id="p1",
            title="Paper 1",
            authors=["Alice"],
            abstract="",
            url="",
            year=None,
            source=PaperSource.SEMANTIC_SCHOLAR,
        )
    ]
    result = generate_year_trend_chart(papers)
    assert result is None


def test_generate_source_distribution_chart(sample_papers: list[PaperMetadata]):
    result = generate_source_distribution_chart(sample_papers)

    assert result is not None
    decoded = base64.b64decode(result)
    assert decoded[:8] == b"\x89PNG\r\n\x1a\n"


def test_generate_source_distribution_chart_empty():
    result = generate_source_distribution_chart([])
    assert result is None


def test_generate_author_frequency_chart(sample_papers: list[PaperMetadata]):
    result = generate_author_frequency_chart(sample_papers)

    assert result is not None
    decoded = base64.b64decode(result)
    assert decoded[:8] == b"\x89PNG\r\n\x1a\n"


def test_generate_author_frequency_chart_empty():
    result = generate_author_frequency_chart([])
    assert result is None


def test_generate_author_frequency_chart_no_authors():
    papers = [
        PaperMetadata(
            paper_id="p1",
            title="Paper 1",
            authors=[],
            abstract="",
            url="",
            year=2023,
            source=PaperSource.SEMANTIC_SCHOLAR,
        )
    ]
    result = generate_author_frequency_chart(papers)
    assert result is None


def test_generate_all_charts(sample_papers: list[PaperMetadata]):
    result = generate_all_charts(sample_papers)

    assert "year_trend" in result
    assert "source_distribution" in result
    assert "author_frequency" in result

    assert result["year_trend"] is not None
    assert result["source_distribution"] is not None
    assert result["author_frequency"] is not None


def test_generate_all_charts_empty():
    result = generate_all_charts([])

    assert result["year_trend"] is None
    assert result["source_distribution"] is None
    assert result["author_frequency"] is None
