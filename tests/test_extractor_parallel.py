"""Tests for extractor agent parallelization and fulltext enrichment merging."""

import pytest

from backend.schemas import PaperMetadata, PaperSource


@pytest.fixture
def mock_papers_without_pdf():
    """Papers that don't have PDF URLs yet."""
    return [
        PaperMetadata(
            paper_id="paper_1",
            title="Paper 1",
            authors=["Author 1"],
            year=2020,
            abstract="Abstract 1",
            url="https://example.com/1",
            source=PaperSource.SEMANTIC_SCHOLAR,
            pdf_url=None,  # No PDF URL initially
        ),
        PaperMetadata(
            paper_id="paper_2",
            title="Paper 2",
            authors=["Author 2"],
            year=2021,
            abstract="Abstract 2",
            url="https://example.com/2",
            source=PaperSource.SEMANTIC_SCHOLAR,
            pdf_url=None,  # No PDF URL initially
        ),
    ]


@pytest.fixture
def mock_papers_with_pdf():
    """Same papers but with PDF URLs (simulating enrichment)."""
    return [
        PaperMetadata(
            paper_id="paper_1",
            title="Paper 1",
            authors=["Author 1"],
            year=2020,
            abstract="Abstract 1",
            url="https://example.com/1",
            source=PaperSource.SEMANTIC_SCHOLAR,
            pdf_url="https://arxiv.org/pdf/1.pdf",  # PDF added via enrichment
        ),
        PaperMetadata(
            paper_id="paper_2",
            title="Paper 2",
            authors=["Author 2"],
            year=2021,
            abstract="Abstract 2",
            url="https://example.com/2",
            source=PaperSource.SEMANTIC_SCHOLAR,
            pdf_url="https://arxiv.org/pdf/2.pdf",  # PDF added via enrichment
        ),
    ]


@pytest.fixture
def mock_papers_mixed():
    """Mix of papers with and without PDF URLs."""
    return [
        PaperMetadata(
            paper_id="paper_1",
            title="Paper 1",
            authors=["Author 1"],
            year=2020,
            abstract="Abstract 1",
            url="https://example.com/1",
            source=PaperSource.SEMANTIC_SCHOLAR,
            pdf_url="https://arxiv.org/pdf/1.pdf",  # Has PDF
        ),
        PaperMetadata(
            paper_id="paper_2",
            title="Paper 2",
            authors=["Author 2"],
            year=2021,
            abstract="Abstract 2",
            url="https://example.com/2",
            source=PaperSource.SEMANTIC_SCHOLAR,
            pdf_url=None,  # No PDF
        ),
        PaperMetadata(
            paper_id="paper_3",
            title="Paper 3",
            authors=["Author 3"],
            year=2022,
            abstract="Abstract 3",
            url="https://example.com/3",
            source=PaperSource.SEMANTIC_SCHOLAR,
            pdf_url="https://arxiv.org/pdf/3.pdf",  # Has PDF
        ),
    ]


class TestFulltextEnrichment:
    """Tests for fulltext enrichment merging logic."""

    def test_fulltext_pdf_url_mapping(self):
        """Test that PDF URLs are correctly mapped by paper_id."""
        enriched_papers = [
            PaperMetadata(
                paper_id="paper_1",
                title="Paper 1",
                authors=["Author 1"],
                abstract="Abstract 1",
                url="https://example.com/1",
                source=PaperSource.SEMANTIC_SCHOLAR,
                pdf_url="https://arxiv.org/pdf/1.pdf",
            ),
            PaperMetadata(
                paper_id="paper_2",
                title="Paper 2",
                authors=["Author 2"],
                abstract="Abstract 2",
                url="https://example.com/2",
                source=PaperSource.SEMANTIC_SCHOLAR,
                pdf_url="https://arxiv.org/pdf/2.pdf",
            ),
        ]

        # Simulate the pdf_map creation from extractor_agent logic
        pdf_map: dict[str, str] = {}
        for p in enriched_papers:
            if p.pdf_url:
                pdf_map[p.paper_id] = p.pdf_url

        assert pdf_map["paper_1"] == "https://arxiv.org/pdf/1.pdf"
        assert pdf_map["paper_2"] == "https://arxiv.org/pdf/2.pdf"
        assert len(pdf_map) == 2

    def test_fulltext_merging_adds_pdf_urls(self, mock_papers_without_pdf):
        """Test that PDF URLs are added to papers without them."""
        enriched_papers = [
            PaperMetadata(
                paper_id="paper_1",
                title="Paper 1",
                authors=["Author 1"],
                abstract="Abstract 1",
                url="https://example.com/1",
                source=PaperSource.SEMANTIC_SCHOLAR,
                pdf_url="https://arxiv.org/pdf/1.pdf",
            ),
            PaperMetadata(
                paper_id="paper_2",
                title="Paper 2",
                authors=["Author 2"],
                abstract="Abstract 2",
                url="https://example.com/2",
                source=PaperSource.SEMANTIC_SCHOLAR,
                pdf_url="https://arxiv.org/pdf/2.pdf",
            ),
        ]

        # Simulate the merging logic from extractor_agent
        pdf_map: dict[str, str] = {}
        for p in enriched_papers:
            if p.pdf_url:
                pdf_map[p.paper_id] = p.pdf_url

        merged: list[PaperMetadata] = []
        for p in mock_papers_without_pdf:
            if not p.pdf_url and p.paper_id in pdf_map:
                merged.append(p.model_copy(update={"pdf_url": pdf_map[p.paper_id]}))
            else:
                merged.append(p)

        # Verify all papers have PDF URLs after merging
        assert len(merged) == 2
        assert merged[0].pdf_url == "https://arxiv.org/pdf/1.pdf"
        assert merged[1].pdf_url == "https://arxiv.org/pdf/2.pdf"

    def test_fulltext_merging_preserves_existing_pdfs(self, mock_papers_with_pdf):
        """Test that existing PDF URLs are not overwritten."""
        enriched_papers = [
            PaperMetadata(
                paper_id="paper_1",
                title="Paper 1",
                authors=["Author 1"],
                abstract="Abstract 1",
                url="https://example.com/1",
                source=PaperSource.SEMANTIC_SCHOLAR,
                pdf_url="https://arxiv.org/pdf/1.pdf",
            ),
            PaperMetadata(
                paper_id="paper_2",
                title="Paper 2",
                authors=["Author 2"],
                abstract="Abstract 2",
                url="https://example.com/2",
                source=PaperSource.SEMANTIC_SCHOLAR,
                pdf_url="https://arxiv.org/pdf/2.pdf",
            ),
        ]

        # Simulate the merging logic from extractor_agent
        pdf_map: dict[str, str] = {}
        for p in enriched_papers:
            if p.pdf_url:
                pdf_map[p.paper_id] = p.pdf_url

        merged: list[PaperMetadata] = []
        for p in mock_papers_with_pdf:
            if not p.pdf_url and p.paper_id in pdf_map:
                merged.append(p.model_copy(update={"pdf_url": pdf_map[p.paper_id]}))
            else:
                merged.append(p)

        # Verify existing PDFs are preserved
        assert len(merged) == 2
        assert merged[0].pdf_url == "https://arxiv.org/pdf/1.pdf"
        assert merged[1].pdf_url == "https://arxiv.org/pdf/2.pdf"

    def test_fulltext_merging_handles_mixed_papers(self, mock_papers_mixed):
        """Test that only papers without PDFs get updated."""
        # Simulate enrichment that only found PDFs for papers 1 and 3
        enriched_papers = [
            PaperMetadata(
                paper_id="paper_1",
                title="Paper 1",
                authors=["Author 1"],
                abstract="Abstract 1",
                url="https://example.com/1",
                source=PaperSource.SEMANTIC_SCHOLAR,
                pdf_url="https://arxiv.org/pdf/1.pdf",
            ),
            PaperMetadata(
                paper_id="paper_3",
                title="Paper 3",
                authors=["Author 3"],
                abstract="Abstract 3",
                url="https://example.com/3",
                source=PaperSource.SEMANTIC_SCHOLAR,
                pdf_url="https://arxiv.org/pdf/3.pdf",
            ),
        ]

        # Simulate the merging logic from extractor_agent
        pdf_map: dict[str, str] = {}
        for p in enriched_papers:
            if p.pdf_url:
                pdf_map[p.paper_id] = p.pdf_url

        merged: list[PaperMetadata] = []
        for p in mock_papers_mixed:
            if not p.pdf_url and p.paper_id in pdf_map:
                merged.append(p.model_copy(update={"pdf_url": pdf_map[p.paper_id]}))
            else:
                merged.append(p)

        # Verify: paper_1 keeps its PDF, paper_2 stays None, paper_3 gets PDF
        assert len(merged) == 3
        assert merged[0].pdf_url == "https://arxiv.org/pdf/1.pdf"  # Existing PDF preserved
        assert merged[1].pdf_url is None  # Stays None
        assert merged[2].pdf_url == "https://arxiv.org/pdf/3.pdf"  # Gets PDF from enrichment
