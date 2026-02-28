from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from backend.schemas import PaperMetadata, PaperSource
from backend.utils.embedder import EmbeddingError
from backend.utils.pdf_parser import PDFParseError
from backend.utils.vector_pipeline import (
    PipelineResult,
    PipelineSummary,
    _build_chunk_payloads,
    _extract_text,
    _process_single_paper,
    run_vector_pipeline,
)
from backend.utils.vector_store import VectorStoreError


def _make_paper(
    paper_id: str = "p1",
    pdf_url: str | None = "https://example.com/paper.pdf",
    abstract: str = "This is a test abstract about machine learning.",
) -> PaperMetadata:
    return PaperMetadata(
        paper_id=paper_id,
        title=f"Paper {paper_id}",
        authors=["Author A", "Author B"],
        abstract=abstract,
        url=f"https://example.com/{paper_id}",
        year=2024,
        pdf_url=pdf_url,
        source=PaperSource.SEMANTIC_SCHOLAR,
    )


@pytest.fixture
def mock_embedder():
    with patch("backend.utils.vector_pipeline.Embedder", autospec=True):
        embedder = AsyncMock()
        embedder.embed_batch = AsyncMock(return_value=[[0.1, 0.2, 0.3]])
        return embedder


@pytest.fixture
def mock_vector_store():
    store = AsyncMock()
    store.ensure_collection_exists = AsyncMock()
    store.upsert_chunks = AsyncMock(return_value=["uuid-1"])
    return store


class TestRunVectorPipeline:
    async def test_skips_papers_without_pdf_url(self, mock_embedder, mock_vector_store):
        papers = [_make_paper(pdf_url=None)]

        summary = await run_vector_pipeline(papers, mock_embedder, mock_vector_store)

        assert summary.total_papers == 0
        assert summary.successful == 0
        mock_vector_store.ensure_collection_exists.assert_not_awaited()

    async def test_processes_papers_with_pdf_url(self, mock_embedder, mock_vector_store):
        papers = [_make_paper()]

        with patch(
            "backend.utils.vector_pipeline.extract_text_from_url",
            new=AsyncMock(return_value="Full text of the paper with enough content to chunk."),
        ):
            with patch("backend.utils.vector_pipeline.TextChunker") as MockChunker:
                mock_chunk = MagicMock()
                mock_chunk.text = "chunk text"
                mock_chunk.chunk_index = 0
                mock_chunk.token_count = 10
                mock_chunk.start_char = 0
                mock_chunk.end_char = 10
                MockChunker.return_value.chunk_text.return_value = [mock_chunk]

                summary = await run_vector_pipeline(papers, mock_embedder, mock_vector_store)

        assert summary.total_papers == 1
        assert summary.successful == 1
        assert summary.total_chunks == 1
        mock_vector_store.ensure_collection_exists.assert_awaited_once()

    async def test_handles_mixed_success_and_failure(self, mock_embedder, mock_vector_store):
        papers = [_make_paper("p1"), _make_paper("p2", abstract="")]

        call_count = 0

        async def extract_side_effect(url):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                return "A" * 200
            raise PDFParseError("corrupt pdf")

        with patch(
            "backend.utils.vector_pipeline.extract_text_from_url",
            new=AsyncMock(side_effect=extract_side_effect),
        ):
            with patch("backend.utils.vector_pipeline.TextChunker") as MockChunker:
                mock_chunk = MagicMock()
                mock_chunk.text = "chunk"
                mock_chunk.chunk_index = 0
                mock_chunk.token_count = 5
                mock_chunk.start_char = 0
                mock_chunk.end_char = 5
                MockChunker.return_value.chunk_text.return_value = [mock_chunk]

                summary = await run_vector_pipeline(papers, mock_embedder, mock_vector_store)

        assert summary.total_papers == 2
        assert summary.successful == 1
        assert summary.failed == 1

    async def test_empty_papers_list(self, mock_embedder, mock_vector_store):
        summary = await run_vector_pipeline([], mock_embedder, mock_vector_store)

        assert summary.total_papers == 0
        assert summary.successful == 0
        assert summary.total_chunks == 0


class TestExtractText:
    async def test_extracts_from_pdf_url(self):
        paper = _make_paper()
        long_text = "A" * 200
        with patch(
            "backend.utils.vector_pipeline.extract_text_from_url",
            new=AsyncMock(return_value=long_text),
        ):
            text = await _extract_text(paper)

        assert text == long_text

    async def test_falls_back_to_abstract_on_pdf_failure(self):
        paper = _make_paper(abstract="Fallback abstract text.")
        with patch(
            "backend.utils.vector_pipeline.extract_text_from_url",
            new=AsyncMock(side_effect=PDFParseError("parse failed")),
        ):
            text = await _extract_text(paper)

        assert text == "Fallback abstract text."

    async def test_falls_back_to_abstract_when_pdf_text_too_short(self):
        paper = _make_paper(abstract="Good abstract.")
        with patch(
            "backend.utils.vector_pipeline.extract_text_from_url",
            new=AsyncMock(return_value="short"),
        ):
            text = await _extract_text(paper)

        assert text == "Good abstract."

    async def test_returns_abstract_when_no_pdf_url(self):
        paper = _make_paper(pdf_url=None, abstract="Abstract only.")
        text = await _extract_text(paper)
        assert text == "Abstract only."


class TestBuildChunkPayloads:
    def test_builds_correct_payload_structure(self):
        paper = _make_paper()
        chunk = MagicMock()
        chunk.chunk_index = 0
        chunk.text = "chunk text"
        chunk.token_count = 10
        chunk.start_char = 0
        chunk.end_char = 10

        payloads = _build_chunk_payloads(paper, [chunk])

        assert len(payloads) == 1
        p = payloads[0]
        assert p["paper_id"] == "p1"
        assert p["title"] == "Paper p1"
        assert p["authors"] == ["Author A", "Author B"]
        assert p["year"] == 2024
        assert p["source"] == "semantic_scholar"
        assert p["chunk_index"] == 0
        assert p["chunk_text"] == "chunk text"
        assert p["token_count"] == 10

    def test_truncates_authors_to_five(self):
        paper = _make_paper()
        paper = paper.model_copy(update={"authors": ["A1", "A2", "A3", "A4", "A5", "A6", "A7"]})
        chunk = MagicMock()
        chunk.chunk_index = 0
        chunk.text = "t"
        chunk.token_count = 1
        chunk.start_char = 0
        chunk.end_char = 1

        payloads = _build_chunk_payloads(paper, [chunk])

        assert len(payloads[0]["authors"]) == 5


class TestProcessSinglePaper:
    async def test_success_path(self):
        paper = _make_paper()
        chunker = MagicMock()
        mock_chunk = MagicMock()
        mock_chunk.text = "chunk"
        mock_chunk.chunk_index = 0
        mock_chunk.token_count = 5
        mock_chunk.start_char = 0
        mock_chunk.end_char = 5
        chunker.chunk_text.return_value = [mock_chunk]

        embedder = AsyncMock()
        embedder.embed_batch = AsyncMock(return_value=[[0.1]])
        vector_store = AsyncMock()
        vector_store.upsert_chunks = AsyncMock(return_value=["uuid-1"])

        with patch(
            "backend.utils.vector_pipeline.extract_text_from_url",
            new=AsyncMock(return_value="Full text content for the paper."),
        ):
            result = await _process_single_paper(paper, chunker, embedder, vector_store)

        assert result.success is True
        assert result.chunk_count == 1
        assert result.point_ids == ["uuid-1"]
        assert result.error is None

    async def test_embedding_error_captured(self):
        paper = _make_paper()
        chunker = MagicMock()
        mock_chunk = MagicMock()
        mock_chunk.text = "chunk"
        mock_chunk.chunk_index = 0
        mock_chunk.token_count = 5
        mock_chunk.start_char = 0
        mock_chunk.end_char = 5
        chunker.chunk_text.return_value = [mock_chunk]

        embedder = AsyncMock()
        embedder.embed_batch = AsyncMock(side_effect=EmbeddingError("api down"))
        vector_store = AsyncMock()

        with patch(
            "backend.utils.vector_pipeline.extract_text_from_url",
            new=AsyncMock(return_value="Full text content for the paper."),
        ):
            result = await _process_single_paper(paper, chunker, embedder, vector_store)

        assert result.success is False
        assert "api down" in result.error

    async def test_vector_store_error_captured(self):
        paper = _make_paper()
        chunker = MagicMock()
        mock_chunk = MagicMock()
        mock_chunk.text = "chunk"
        mock_chunk.chunk_index = 0
        mock_chunk.token_count = 5
        mock_chunk.start_char = 0
        mock_chunk.end_char = 5
        chunker.chunk_text.return_value = [mock_chunk]

        embedder = AsyncMock()
        embedder.embed_batch = AsyncMock(return_value=[[0.1]])
        vector_store = AsyncMock()
        vector_store.upsert_chunks = AsyncMock(side_effect=VectorStoreError("upsert failed"))

        with patch(
            "backend.utils.vector_pipeline.extract_text_from_url",
            new=AsyncMock(return_value="Full text content for the paper."),
        ):
            result = await _process_single_paper(paper, chunker, embedder, vector_store)

        assert result.success is False
        assert "upsert failed" in result.error


class TestPipelineDataclasses:
    def test_pipeline_result_defaults(self):
        r = PipelineResult(paper_id="p1", success=True)
        assert r.chunk_count == 0
        assert r.point_ids == []
        assert r.error is None
        assert r.duration_ms == 0.0

    def test_pipeline_summary_defaults(self):
        s = PipelineSummary()
        assert s.total_papers == 0
        assert s.successful == 0
        assert s.failed == 0
        assert s.total_chunks == 0
        assert s.results == []
