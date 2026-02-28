"""Text chunking utilities for embedding generation.

This module provides token-aware text chunking that respects paragraph boundaries
and maintains overlap between chunks for context continuity.
"""

import logging
from typing import Any

import tiktoken
from pydantic import BaseModel, Field

from backend.constants import CHUNK_OVERLAP_TOKENS, CHUNK_SIZE_TOKENS, TIKTOKEN_MODEL

logger = logging.getLogger(__name__)


class TextChunk(BaseModel):
    text: str = Field(description="The text content of the chunk")
    chunk_index: int = Field(description="Index of this chunk in the sequence")
    token_count: int = Field(description="Number of tokens in this chunk")
    start_char: int = Field(description="Start character position in original text")
    end_char: int = Field(description="End character position in original text")
    page_start: int | None = Field(default=None, description="Starting page number")
    page_end: int | None = Field(default=None, description="Ending page number")
    metadata: dict[str, Any] = Field(default_factory=dict, description="Additional metadata")


class TextChunker:
    """Token-aware text chunker with paragraph boundary respect."""

    def __init__(
        self,
        chunk_size: int = CHUNK_SIZE_TOKENS,
        chunk_overlap: int = CHUNK_OVERLAP_TOKENS,
        model: str = TIKTOKEN_MODEL,
    ):
        """Initialize text chunker.

        Args:
            chunk_size: Maximum tokens per chunk
            chunk_overlap: Number of overlapping tokens between chunks
            model: Tiktoken model name for token counting
        """
        self.chunk_size = chunk_size
        self.chunk_overlap = chunk_overlap
        self.encoding = tiktoken.get_encoding(model)
        logger.info(
            "TextChunker initialized: chunk_size=%d, overlap=%d, model=%s",
            chunk_size,
            chunk_overlap,
            model,
        )

    def chunk_text(self, text: str, metadata: dict[str, Any] | None = None) -> list[TextChunk]:
        """Chunk text into token-sized pieces with overlap.

        Args:
            text: Text to chunk
            metadata: Optional metadata to attach to all chunks

        Returns:
            List of TextChunk objects
        """
        if not text or not text.strip():
            logger.warning("Empty text provided to chunker")
            return []

        metadata = metadata or {}

        # Split into paragraphs
        paragraphs = self._split_by_paragraphs(text)
        logger.debug("Split text into %d paragraphs", len(paragraphs))

        # Create chunks with overlap
        chunks = self._create_chunks_with_overlap(paragraphs, text, metadata)

        logger.info(
            "Created %d chunks from text (length=%d chars, %d tokens)",
            len(chunks),
            len(text),
            sum(c.token_count for c in chunks),
        )

        return chunks

    def _split_by_paragraphs(self, text: str) -> list[str]:
        """Split text into paragraphs.

        Args:
            text: Text to split

        Returns:
            List of paragraph strings
        """
        # Split on double newlines (paragraph breaks)
        paragraphs = text.split("\n\n")

        # Filter empty paragraphs and strip whitespace
        paragraphs = [p.strip() for p in paragraphs if p.strip()]

        return paragraphs

    def _count_tokens(self, text: str) -> int:
        """Count tokens in text.

        Args:
            text: Text to count tokens for

        Returns:
            Number of tokens
        """
        return len(self.encoding.encode(text))

    def _create_chunks_with_overlap(
        self, paragraphs: list[str], original_text: str, metadata: dict[str, Any]
    ) -> list[TextChunk]:
        """Create chunks from paragraphs with overlap.

        Args:
            paragraphs: List of paragraph strings
            original_text: Original full text for character position tracking
            metadata: Metadata to attach to chunks

        Returns:
            List of TextChunk objects
        """
        chunks: list[TextChunk] = []
        current_chunk_text = ""
        current_chunk_tokens = 0
        chunk_index = 0
        start_char = 0

        # Track previous chunk text for overlap
        previous_chunk_text = ""

        for para in paragraphs:
            para_tokens = self._count_tokens(para)

            # If single paragraph exceeds chunk size, split it
            if para_tokens > self.chunk_size:
                # Finish current chunk if any
                if current_chunk_text:
                    end_char = original_text.find(current_chunk_text, start_char) + len(
                        current_chunk_text
                    )
                    chunks.append(
                        TextChunk(
                            text=current_chunk_text.strip(),
                            chunk_index=chunk_index,
                            token_count=current_chunk_tokens,
                            start_char=start_char,
                            end_char=end_char,
                            metadata=metadata.copy(),
                        )
                    )
                    chunk_index += 1
                    previous_chunk_text = current_chunk_text
                    current_chunk_text = ""
                    current_chunk_tokens = 0

                # Split large paragraph by sentences
                sentences = para.split(". ")
                for sentence in sentences:
                    sentence = sentence.strip()
                    if not sentence:
                        continue

                    sentence_tokens = self._count_tokens(sentence)

                    if current_chunk_tokens + sentence_tokens > self.chunk_size:
                        # Save current chunk
                        if current_chunk_text:
                            end_char = original_text.find(current_chunk_text, start_char) + len(
                                current_chunk_text
                            )
                            chunks.append(
                                TextChunk(
                                    text=current_chunk_text.strip(),
                                    chunk_index=chunk_index,
                                    token_count=current_chunk_tokens,
                                    start_char=start_char,
                                    end_char=end_char,
                                    metadata=metadata.copy(),
                                )
                            )
                            chunk_index += 1
                            previous_chunk_text = current_chunk_text

                        # Start new chunk with overlap
                        if previous_chunk_text and self.chunk_overlap > 0:
                            overlap_text = self._get_overlap_text(previous_chunk_text)
                            current_chunk_text = overlap_text + " " + sentence
                            current_chunk_tokens = self._count_tokens(current_chunk_text)
                            start_char = original_text.find(overlap_text, start_char)
                        else:
                            current_chunk_text = sentence
                            current_chunk_tokens = sentence_tokens
                            start_char = original_text.find(sentence, start_char)
                    else:
                        # Add to current chunk
                        if current_chunk_text:
                            current_chunk_text += ". " + sentence
                        else:
                            current_chunk_text = sentence
                        current_chunk_tokens += sentence_tokens

                continue

            # Check if adding this paragraph exceeds chunk size
            if current_chunk_tokens + para_tokens > self.chunk_size:
                # Save current chunk
                if current_chunk_text:
                    end_char = original_text.find(current_chunk_text, start_char) + len(
                        current_chunk_text
                    )
                    chunks.append(
                        TextChunk(
                            text=current_chunk_text.strip(),
                            chunk_index=chunk_index,
                            token_count=current_chunk_tokens,
                            start_char=start_char,
                            end_char=end_char,
                            metadata=metadata.copy(),
                        )
                    )
                    chunk_index += 1
                    previous_chunk_text = current_chunk_text

                # Start new chunk with overlap
                if previous_chunk_text and self.chunk_overlap > 0:
                    overlap_text = self._get_overlap_text(previous_chunk_text)
                    current_chunk_text = overlap_text + "\n\n" + para
                    current_chunk_tokens = self._count_tokens(current_chunk_text)
                    start_char = original_text.find(overlap_text, start_char)
                else:
                    current_chunk_text = para
                    current_chunk_tokens = para_tokens
                    start_char = original_text.find(para, start_char)
            else:
                # Add to current chunk
                if current_chunk_text:
                    current_chunk_text += "\n\n" + para
                else:
                    current_chunk_text = para
                current_chunk_tokens += para_tokens

        # Add final chunk
        if current_chunk_text:
            end_char = original_text.find(current_chunk_text, start_char) + len(current_chunk_text)
            if end_char < start_char:  # Not found, use end of text
                end_char = len(original_text)

            chunks.append(
                TextChunk(
                    text=current_chunk_text.strip(),
                    chunk_index=chunk_index,
                    token_count=current_chunk_tokens,
                    start_char=start_char,
                    end_char=end_char,
                    metadata=metadata.copy(),
                )
            )

        return chunks

    def _get_overlap_text(self, text: str) -> str:
        """Get overlap text from end of previous chunk.

        Args:
            text: Previous chunk text

        Returns:
            Overlap text (last N tokens)
        """
        tokens = self.encoding.encode(text)

        if len(tokens) <= self.chunk_overlap:
            return text

        # Get last N tokens
        overlap_tokens = tokens[-self.chunk_overlap :]
        overlap_text = self.encoding.decode(overlap_tokens)

        return overlap_text
