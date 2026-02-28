"""Unit tests for backend.utils.text_chunker."""

import pytest

from backend.constants import CHUNK_OVERLAP_TOKENS, CHUNK_SIZE_TOKENS, TIKTOKEN_MODEL
from backend.utils.text_chunker import TextChunk, TextChunker


class TestTextChunkModel:
    def test_text_chunk_fields_are_set(self):
        chunk = TextChunk(
            text="chunk body",
            chunk_index=0,
            token_count=3,
            start_char=0,
            end_char=10,
            metadata={"source": "doc"},
        )

        assert chunk.text == "chunk body"
        assert chunk.chunk_index == 0
        assert chunk.token_count == 3
        assert chunk.start_char == 0
        assert chunk.end_char == 10
        assert chunk.metadata == {"source": "doc"}

    def test_text_chunk_metadata_defaults_to_empty_dict(self):
        chunk = TextChunk(text="x", chunk_index=1, token_count=1, start_char=0, end_char=1)
        assert chunk.metadata == {}

    def test_text_chunk_requires_required_fields(self):
        with pytest.raises(Exception):
            TextChunk(text="missing fields")


class TestTextChunkerInit:
    def test_init_uses_constants_by_default(self):
        chunker = TextChunker()
        assert chunker.chunk_size == CHUNK_SIZE_TOKENS
        assert chunker.chunk_overlap == CHUNK_OVERLAP_TOKENS
        assert chunker.encoding.name == TIKTOKEN_MODEL

    def test_init_accepts_custom_values(self):
        chunker = TextChunker(chunk_size=64, chunk_overlap=8, model="cl100k_base")
        assert chunker.chunk_size == 64
        assert chunker.chunk_overlap == 8
        assert chunker.encoding.name == "cl100k_base"


class TestSplitByParagraphs:
    def test_split_by_paragraphs_filters_empty_items(self):
        chunker = TextChunker()
        text = "\n\nPara one\n\n\n\nPara two\n\n   \n\nPara three\n\n"
        parts = chunker._split_by_paragraphs(text)
        assert parts == ["Para one", "Para two", "Para three"]


class TestOverlapText:
    def test_get_overlap_text_returns_full_text_when_shorter_than_overlap(self):
        chunker = TextChunker(chunk_size=100, chunk_overlap=50)
        text = "short text"
        assert chunker._get_overlap_text(text) == text

    def test_get_overlap_text_returns_last_n_tokens(self):
        chunker = TextChunker(chunk_size=200, chunk_overlap=5)
        text = "one two three four five six seven eight nine ten"
        overlap = chunker._get_overlap_text(text)
        overlap_tokens = chunker.encoding.encode(overlap)
        assert len(overlap_tokens) <= 5
        assert overlap in text


class TestChunkText:
    def test_chunk_text_returns_empty_for_empty_and_whitespace(self):
        chunker = TextChunker()
        assert chunker.chunk_text("") == []
        assert chunker.chunk_text("   \n\n  ") == []

    def test_chunk_text_single_paragraph_single_chunk(self):
        chunker = TextChunker(chunk_size=200, chunk_overlap=10)
        text = "This is a short paragraph with enough words to remain one chunk."
        chunks = chunker.chunk_text(text, metadata={"doc": "a"})
        assert len(chunks) == 1
        assert chunks[0].text == text
        assert chunks[0].chunk_index == 0
        assert chunks[0].metadata == {"doc": "a"}
        assert chunks[0].start_char >= 0
        assert chunks[0].end_char >= chunks[0].start_char

    def test_chunk_text_multiple_paragraphs_preserves_chunk_index_sequence(self):
        chunker = TextChunker(chunk_size=18, chunk_overlap=4)
        text = (
            "Paragraph one has several words to consume token budget.\n\n"
            "Paragraph two also has several words and should push chunking.\n\n"
            "Paragraph three continues to force additional chunk creation."
        )
        chunks = chunker.chunk_text(text)
        assert len(chunks) >= 2
        assert [c.chunk_index for c in chunks] == list(range(len(chunks)))
        for chunk in chunks:
            assert chunk.start_char >= 0
            assert chunk.end_char >= chunk.start_char

    def test_chunk_text_overlap_appears_between_consecutive_chunks(self):
        chunker = TextChunker(chunk_size=20, chunk_overlap=6)
        text = (
            "First paragraph contains enough content to become chunk material.\n\n"
            "Second paragraph extends the context so overlap is needed.\n\n"
            "Third paragraph gives additional text to force another boundary."
        )
        chunks = chunker.chunk_text(text)
        assert len(chunks) >= 2

        for i in range(1, len(chunks)):
            expected_overlap = chunker._get_overlap_text(chunks[i - 1].text)
            assert expected_overlap.strip()
            # Decoding token slices may include/omit leading whitespace.
            assert expected_overlap.strip() in chunks[i].text

    def test_chunk_text_respects_token_limits_for_non_oversized_inputs(self):
        chunker = TextChunker(chunk_size=25, chunk_overlap=5)
        text = "\n\n".join(
            [f"Paragraph {i} has tokens for test budget control." for i in range(1, 8)]
        )
        chunks = chunker.chunk_text(text)
        assert chunks
        # For paragraph-based splitting, chunks can slightly exceed due to overlap + paragraph add,
        # but should stay reasonably near configured size.
        for chunk in chunks:
            assert chunk.token_count <= chunker.chunk_size + chunker.chunk_overlap + 10

    def test_chunk_text_single_word(self):
        chunker = TextChunker(chunk_size=5, chunk_overlap=1)
        chunks = chunker.chunk_text("word")
        assert len(chunks) == 1
        assert chunks[0].text == "word"
        assert chunks[0].chunk_index == 0

    def test_chunk_text_very_long_single_sentence_single_chunk_when_no_sentence_boundaries(self):
        chunker = TextChunker(chunk_size=20, chunk_overlap=5)
        sentence = " ".join(["token"] * 200)
        chunks = chunker.chunk_text(sentence)
        # Implementation only splits oversized paragraphs on ". " sentence boundaries.
        assert len(chunks) == 1
        assert chunks[0].token_count > chunker.chunk_size
        assert chunks[0].chunk_index == 0


class TestCreateChunksWithOverlap:
    def test_create_chunks_with_overlap_splits_large_paragraph_by_sentences(self):
        chunker = TextChunker(chunk_size=20, chunk_overlap=5)
        paragraph = ". ".join(
            [
                "Sentence one has multiple words for token usage",
                "Sentence two also has many words for chunk growth",
                "Sentence three continues the pattern for splitting",
                "Sentence four keeps adding more words here",
            ]
        )
        original = paragraph
        chunks = chunker._create_chunks_with_overlap([paragraph], original, metadata={"k": "v"})

        assert len(chunks) >= 2
        assert [c.chunk_index for c in chunks] == list(range(len(chunks)))
        for chunk in chunks:
            assert chunk.metadata == {"k": "v"}
            assert chunk.start_char >= 0
            assert chunk.end_char >= chunk.start_char
