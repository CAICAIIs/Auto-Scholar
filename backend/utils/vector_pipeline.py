"""Vector ingestion pipeline: PDF → chunks → embeddings → Qdrant.

Orchestrates the full vector pipeline for approved papers. Designed to be
called from extractor_agent with graceful degradation on any failure.
"""

import logging
import time
from dataclasses import dataclass, field
from typing import Any

from backend.constants import (
    CHUNK_OVERLAP_TOKENS,
    CHUNK_SIZE_TOKENS,
    TIKTOKEN_MODEL,
)
from backend.schemas import PaperMetadata
from backend.utils.embedder import Embedder, EmbeddingError
from backend.utils.pdf_parser import PDFParseError, extract_text_from_url
from backend.utils.text_chunker import TextChunk, TextChunker
from backend.utils.vector_store import QdrantVectorStore, VectorStoreError

logger = logging.getLogger(__name__)


@dataclass
class PipelineResult:
    """Result of processing a single paper through the vector pipeline."""

    paper_id: str
    success: bool
    chunk_count: int = 0
    point_ids: list[str] = field(default_factory=list)
    error: str | None = None
    duration_ms: float = 0.0


@dataclass
class PipelineSummary:
    """Aggregate result of the full pipeline run."""

    total_papers: int = 0
    successful: int = 0
    failed: int = 0
    total_chunks: int = 0
    total_duration_ms: float = 0.0
    results: list[PipelineResult] = field(default_factory=list)


async def run_vector_pipeline(
    papers: list[PaperMetadata],
    embedder: Embedder,
    vector_store: QdrantVectorStore,
) -> PipelineSummary:
    """Run the full vector pipeline for a list of papers.

    For each paper with a pdf_url:
    1. Extract text from PDF
    2. Chunk text into token-sized pieces
    3. Generate embeddings (with Redis caching)
    4. Upsert chunks + embeddings into Qdrant

    Args:
        papers: Papers to process (only those with pdf_url are processed)
        embedder: Embedder instance (with Redis caching)
        vector_store: Qdrant vector store instance

    Returns:
        PipelineSummary with per-paper results
    """
    start = time.perf_counter()

    papers_with_pdf = [p for p in papers if p.pdf_url]
    if not papers_with_pdf:
        logger.info("vector_pipeline: no papers with PDF URLs, skipping")
        return PipelineSummary()

    await vector_store.ensure_collection_exists()

    chunker = TextChunker(
        chunk_size=CHUNK_SIZE_TOKENS,
        chunk_overlap=CHUNK_OVERLAP_TOKENS,
        model=TIKTOKEN_MODEL,
    )

    summary = PipelineSummary(total_papers=len(papers_with_pdf))

    for paper in papers_with_pdf:
        result = await _process_single_paper(paper, chunker, embedder, vector_store)
        summary.results.append(result)
        if result.success:
            summary.successful += 1
            summary.total_chunks += result.chunk_count
        else:
            summary.failed += 1

    summary.total_duration_ms = (time.perf_counter() - start) * 1000

    logger.info(
        "vector_pipeline: processed %d papers — %d succeeded, %d failed, %d total chunks in %.0fms",
        summary.total_papers,
        summary.successful,
        summary.failed,
        summary.total_chunks,
        summary.total_duration_ms,
    )

    return summary


async def _process_single_paper(
    paper: PaperMetadata,
    chunker: TextChunker,
    embedder: Embedder,
    vector_store: QdrantVectorStore,
) -> PipelineResult:
    """Process a single paper through the vector pipeline."""
    start = time.perf_counter()
    result = PipelineResult(paper_id=paper.paper_id, success=False)

    try:
        full_text = await _extract_text(paper)
        if not full_text:
            result.error = "empty text after extraction"
            result.duration_ms = (time.perf_counter() - start) * 1000
            return result

        chunks = chunker.chunk_text(
            full_text,
            metadata={
                "paper_id": paper.paper_id,
                "title": paper.title,
                "year": paper.year,
                "source": paper.source.value if paper.source else "unknown",
            },
        )

        if not chunks:
            result.error = "no chunks produced"
            result.duration_ms = (time.perf_counter() - start) * 1000
            return result

        chunk_texts = [c.text for c in chunks]
        embeddings = await embedder.embed_batch(chunk_texts)

        chunk_payloads = _build_chunk_payloads(paper, chunks)
        point_ids = await vector_store.upsert_chunks(chunk_payloads, embeddings)

        result.success = True
        result.chunk_count = len(chunks)
        result.point_ids = point_ids

    except (PDFParseError, EmbeddingError, VectorStoreError) as e:
        logger.warning(
            "vector_pipeline: failed for paper %s: %s",
            paper.paper_id,
            str(e),
        )
        result.error = str(e)
    except Exception as e:
        logger.error(
            "vector_pipeline: unexpected error for paper %s: %s",
            paper.paper_id,
            str(e),
        )
        result.error = str(e)

    result.duration_ms = (time.perf_counter() - start) * 1000
    return result


async def _extract_text(paper: PaperMetadata) -> str:
    """Extract text from paper PDF, falling back to abstract."""
    if paper.pdf_url:
        try:
            text = await extract_text_from_url(paper.pdf_url)
            if text and len(text) > 100:
                return text
        except PDFParseError:
            logger.warning(
                "vector_pipeline: PDF parse failed for %s, falling back to abstract",
                paper.paper_id,
            )

    return paper.abstract or ""


def _build_chunk_payloads(
    paper: PaperMetadata,
    chunks: list[TextChunk],
) -> list[dict[str, Any]]:
    """Build Qdrant payload dicts from paper metadata and chunks."""
    payloads = []
    for chunk in chunks:
        payload = {
            "paper_id": paper.paper_id,
            "title": paper.title,
            "authors": paper.authors[:5] if paper.authors else [],
            "year": paper.year,
            "source": paper.source.value if paper.source else "unknown",
            "chunk_index": chunk.chunk_index,
            "chunk_text": chunk.text,
            "token_count": chunk.token_count,
            "start_char": chunk.start_char,
            "end_char": chunk.end_char,
            "page_start": chunk.page_start,
            "page_end": chunk.page_end,
        }
        payloads.append(payload)
    return payloads
