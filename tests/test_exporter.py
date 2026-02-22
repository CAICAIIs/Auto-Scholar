import pytest

from backend.schemas import CitationStyle, DraftOutput, PaperMetadata, ReviewSection
from backend.utils.exporter import (
    export_to_docx,
    export_to_markdown,
    format_citation,
    format_references,
)


@pytest.fixture
def sample_draft() -> DraftOutput:
    return DraftOutput(
        title="Test Literature Review",
        sections=[
            ReviewSection(
                heading="Introduction",
                content="This is the introduction section with citation [1].",
                cited_paper_ids=["paper1"],
            ),
            ReviewSection(
                heading="Methods",
                content="This section discusses methods from [1] and [2].",
                cited_paper_ids=["paper1", "paper2"],
            ),
        ],
    )


@pytest.fixture
def sample_papers() -> list[PaperMetadata]:
    return [
        PaperMetadata(
            paper_id="paper1",
            title="First Paper Title",
            authors=["Author A", "Author B", "Author C", "Author D"],
            abstract="Abstract of first paper",
            url="https://example.com/paper1",
            year=2023,
        ),
        PaperMetadata(
            paper_id="paper2",
            title="Second Paper Title",
            authors=["Author X", "Author Y"],
            abstract="Abstract of second paper",
            url="https://example.com/paper2",
            year=2024,
        ),
    ]


@pytest.fixture
def single_author_paper() -> PaperMetadata:
    return PaperMetadata(
        paper_id="single",
        title="Single Author Paper",
        authors=["Solo Author"],
        abstract="Abstract",
        url="https://example.com/single",
        year=2022,
    )


def test_export_to_markdown(sample_draft: DraftOutput, sample_papers: list[PaperMetadata]):
    result = export_to_markdown(sample_draft, sample_papers)

    assert "# Test Literature Review" in result
    assert "## Introduction" in result
    assert "## Methods" in result
    assert "## References" in result
    assert "First Paper Title" in result
    assert "Second Paper Title" in result
    assert "2023" in result
    assert "2024" in result
    assert "https://example.com/paper1" in result


def test_export_to_markdown_empty_papers(sample_draft: DraftOutput):
    result = export_to_markdown(sample_draft, [])

    assert "# Test Literature Review" in result
    assert "## References" not in result


def test_export_to_docx(sample_draft: DraftOutput, sample_papers: list[PaperMetadata]):
    result = export_to_docx(sample_draft, sample_papers)

    assert isinstance(result, bytes)
    assert len(result) > 0
    assert result[:4] == b"PK\x03\x04"


def test_export_to_docx_empty_papers(sample_draft: DraftOutput):
    result = export_to_docx(sample_draft, [])

    assert isinstance(result, bytes)
    assert len(result) > 0


def test_format_citation_apa(sample_papers: list[PaperMetadata]):
    paper = sample_papers[0]
    result = format_citation(paper, 1, CitationStyle.APA)

    assert "Author A, Author B, Author C, & Author D" in result
    assert "(2023)" in result
    assert "First Paper Title" in result
    assert "https://example.com/paper1" in result


def test_format_citation_apa_two_authors(sample_papers: list[PaperMetadata]):
    paper = sample_papers[1]
    result = format_citation(paper, 2, CitationStyle.APA)

    assert "Author X & Author Y" in result
    assert "(2024)" in result


def test_format_citation_apa_single_author(single_author_paper: PaperMetadata):
    result = format_citation(single_author_paper, 1, CitationStyle.APA)

    assert "Solo Author" in result
    assert "(2022)" in result


def test_format_citation_mla(sample_papers: list[PaperMetadata]):
    paper = sample_papers[0]
    result = format_citation(paper, 1, CitationStyle.MLA)

    assert "Author A, et al." in result
    assert '"First Paper Title."' in result
    assert "2023" in result


def test_format_citation_mla_two_authors(sample_papers: list[PaperMetadata]):
    paper = sample_papers[1]
    result = format_citation(paper, 2, CitationStyle.MLA)

    assert "Author X, and Author Y" in result


def test_format_citation_ieee(sample_papers: list[PaperMetadata]):
    paper = sample_papers[0]
    result = format_citation(paper, 1, CitationStyle.IEEE)

    assert "[1]" in result
    assert "Author A et al." in result
    assert '"First Paper Title,"' in result
    assert "[Online]. Available:" in result


def test_format_citation_ieee_three_authors():
    paper = PaperMetadata(
        paper_id="three",
        title="Three Author Paper",
        authors=["A", "B", "C"],
        abstract="Abstract",
        url="",
        year=2021,
    )
    result = format_citation(paper, 3, CitationStyle.IEEE)

    assert "[3]" in result
    assert "A, B, C" in result


def test_format_citation_gbt7714(sample_papers: list[PaperMetadata]):
    paper = sample_papers[0]
    result = format_citation(paper, 1, CitationStyle.GB_T7714)

    assert "[1]" in result
    assert "Author A, Author B, Author C, 等" in result
    assert "[J]" in result


def test_format_citation_gbt7714_three_authors():
    paper = PaperMetadata(
        paper_id="three",
        title="Three Author Paper",
        authors=["张三", "李四", "王五"],
        abstract="Abstract",
        url="",
        year=2021,
    )
    result = format_citation(paper, 1, CitationStyle.GB_T7714)

    assert "张三, 李四, 王五" in result
    assert "等" not in result


def test_format_references_all_styles(sample_papers: list[PaperMetadata]):
    for style in CitationStyle:
        refs = format_references(sample_papers, style)
        assert len(refs) == 2
        assert all(isinstance(r, str) for r in refs)


def test_export_with_different_citation_styles(
    sample_draft: DraftOutput, sample_papers: list[PaperMetadata]
):
    for style in CitationStyle:
        md_result = export_to_markdown(sample_draft, sample_papers, style)
        assert "## References" in md_result

        docx_result = export_to_docx(sample_draft, sample_papers, style)
        assert isinstance(docx_result, bytes)
        assert len(docx_result) > 0
