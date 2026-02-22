import pytest
from unittest.mock import AsyncMock, patch, MagicMock

from app.schemas import PaperMetadata, PaperSource
from app.utils.fulltext_api import (
    resolve_pdf_url,
    enrich_paper_with_fulltext,
    enrich_papers_with_fulltext,
    _normalize_doi,
    _extract_pdf_from_unpaywall,
    _extract_pdf_from_openalex,
)


def test_normalize_doi():
    assert _normalize_doi("10.1234/test") == "10.1234/test"
    assert _normalize_doi("https://doi.org/10.1234/TEST") == "10.1234/test"
    assert _normalize_doi("http://dx.doi.org/10.1234/Test") == "10.1234/test"
    assert _normalize_doi("  10.1234/test  ") == "10.1234/test"


def test_extract_pdf_from_unpaywall_best_location():
    data = {
        "best_oa_location": {"pdf_url": "https://example.com/best.pdf"},
        "oa_locations": [{"pdf_url": "https://example.com/other.pdf"}],
    }
    assert _extract_pdf_from_unpaywall(data) == "https://example.com/best.pdf"


def test_extract_pdf_from_unpaywall_fallback():
    data = {
        "best_oa_location": {},
        "oa_locations": [
            {"landing_page_url": "https://example.com"},
            {"pdf_url": "https://example.com/fallback.pdf"},
        ],
    }
    assert _extract_pdf_from_unpaywall(data) == "https://example.com/fallback.pdf"


def test_extract_pdf_from_unpaywall_none():
    data = {"best_oa_location": None, "oa_locations": []}
    assert _extract_pdf_from_unpaywall(data) is None


def test_extract_pdf_from_openalex_oa_url():
    work = {"open_access": {"oa_url": "https://example.com/paper.pdf"}}
    assert _extract_pdf_from_openalex(work) == "https://example.com/paper.pdf"


def test_extract_pdf_from_openalex_best_location():
    work = {
        "open_access": {"oa_url": "https://example.com/landing"},
        "best_oa_location": {"pdf_url": "https://example.com/best.pdf"},
    }
    assert _extract_pdf_from_openalex(work) == "https://example.com/best.pdf"


def test_extract_pdf_from_openalex_primary_location():
    work = {
        "open_access": {},
        "best_oa_location": {},
        "primary_location": {"pdf_url": "https://example.com/primary.pdf"},
    }
    assert _extract_pdf_from_openalex(work) == "https://example.com/primary.pdf"


def test_extract_pdf_from_openalex_locations():
    work = {
        "open_access": {},
        "locations": [
            {"landing_page_url": "https://example.com"},
            {"pdf_url": "https://example.com/loc.pdf"},
        ],
    }
    assert _extract_pdf_from_openalex(work) == "https://example.com/loc.pdf"


def test_extract_pdf_from_openalex_none():
    work = {"open_access": {}, "locations": []}
    assert _extract_pdf_from_openalex(work) is None


@pytest.fixture
def sample_paper() -> PaperMetadata:
    return PaperMetadata(
        paper_id="test123",
        title="Test Paper Title",
        authors=["Author A"],
        abstract="Test abstract",
        url="https://example.com/paper",
        year=2023,
        doi="10.1234/test",
        source=PaperSource.SEMANTIC_SCHOLAR,
    )


@pytest.fixture
def paper_without_doi() -> PaperMetadata:
    return PaperMetadata(
        paper_id="test456",
        title="Another Test Paper",
        authors=["Author B"],
        abstract="Another abstract",
        url="https://example.com/paper2",
        year=2022,
        source=PaperSource.ARXIV,
    )


async def test_resolve_pdf_url_with_doi():
    mock_unpaywall_response = {
        "best_oa_location": {"pdf_url": "https://example.com/paper.pdf"}
    }
    
    with patch("app.utils.fulltext_api._fetch_json", new_callable=AsyncMock) as mock_fetch:
        mock_fetch.return_value = mock_unpaywall_response
        
        pdf_url, doi = await resolve_pdf_url(
            title="Test Paper",
            doi="10.1234/test",
        )
        
        assert pdf_url == "https://example.com/paper.pdf"
        assert doi == "10.1234/test"


async def test_resolve_pdf_url_fallback_to_openalex():
    with patch("app.utils.fulltext_api._fetch_json", new_callable=AsyncMock) as mock_fetch:
        mock_fetch.side_effect = [
            None,
            {"open_access": {"oa_url": "https://openalex.com/paper.pdf"}},
        ]
        
        pdf_url, doi = await resolve_pdf_url(
            title="Test Paper",
            doi="10.1234/test",
        )
        
        assert pdf_url == "https://openalex.com/paper.pdf"


async def test_resolve_pdf_url_title_search():
    with patch("app.utils.fulltext_api._fetch_json", new_callable=AsyncMock) as mock_fetch:
        mock_fetch.return_value = {
            "results": [
                {
                    "title": "Test Paper Title",
                    "doi": "https://doi.org/10.5678/found",
                    "best_oa_location": {"pdf_url": "https://found.com/paper.pdf"},
                }
            ]
        }
        
        pdf_url, doi = await resolve_pdf_url(
            title="Test Paper Title",
            doi=None,
        )
        
        assert pdf_url == "https://found.com/paper.pdf"
        assert doi == "10.5678/found"


async def test_enrich_paper_with_fulltext(sample_paper: PaperMetadata):
    with patch("app.utils.fulltext_api.resolve_pdf_url", new_callable=AsyncMock) as mock_resolve:
        mock_resolve.return_value = ("https://example.com/enriched.pdf", "10.1234/test")
        
        enriched = await enrich_paper_with_fulltext(sample_paper)
        
        assert enriched.pdf_url == "https://example.com/enriched.pdf"
        assert enriched.doi == "10.1234/test"


async def test_enrich_paper_already_has_pdf(sample_paper: PaperMetadata):
    paper_with_pdf = sample_paper.model_copy(update={"pdf_url": "https://existing.com/paper.pdf"})
    
    with patch("app.utils.fulltext_api.resolve_pdf_url", new_callable=AsyncMock) as mock_resolve:
        enriched = await enrich_paper_with_fulltext(paper_with_pdf)
        
        mock_resolve.assert_not_called()
        assert enriched.pdf_url == "https://existing.com/paper.pdf"


async def test_enrich_papers_with_fulltext():
    papers = [
        PaperMetadata(
            paper_id="p1",
            title="Paper 1",
            authors=["A"],
            abstract="",
            url="",
            year=2023,
            source=PaperSource.SEMANTIC_SCHOLAR,
        ),
        PaperMetadata(
            paper_id="p2",
            title="Paper 2",
            authors=["B"],
            abstract="",
            url="",
            year=2022,
            source=PaperSource.ARXIV,
        ),
    ]
    
    with patch("app.utils.fulltext_api.resolve_pdf_url", new_callable=AsyncMock) as mock_resolve:
        mock_resolve.side_effect = [
            ("https://example.com/p1.pdf", "10.1/p1"),
            (None, None),
        ]
        
        enriched = await enrich_papers_with_fulltext(papers, concurrency=2)
        
        assert len(enriched) == 2
        assert enriched[0].pdf_url == "https://example.com/p1.pdf"
        assert enriched[0].doi == "10.1/p1"
        assert enriched[1].pdf_url is None
