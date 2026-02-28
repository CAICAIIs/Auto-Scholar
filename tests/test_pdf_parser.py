"""Unit tests for PDF parsing utilities."""

from __future__ import annotations

from unittest.mock import AsyncMock, Mock, patch

import pytest

from backend.constants import PDF_EXTRACTION_TIMEOUT
from backend.utils.pdf_parser import (
    PDFParseError,
    _clean_text,
    _extract_text_from_bytes,
    extract_text_from_minio,
    extract_text_from_url,
)


def test_clean_text_removes_page_numbers_and_normalizes_whitespace() -> None:
    raw = "  Introduction  \n\n1\n\n  This is line one.  \n\n2\nConclusion  "

    cleaned = _clean_text(raw)

    assert cleaned == "Introduction\nThis is line one.\nConclusion"


def test_clean_text_filters_short_non_alnum_lines() -> None:
    raw = "Valid line\n***\n--\n?\nAnother valid line"

    cleaned = _clean_text(raw)

    assert cleaned == "Valid line\nAnother valid line"


def test_clean_text_keeps_short_alnum_lines() -> None:
    raw = "A1\nB2\nText body"

    cleaned = _clean_text(raw)

    assert cleaned == "A1\nB2\nText body"


def test_extract_text_from_bytes_collects_pages_and_cleans() -> None:
    page1 = Mock()
    page1.extract_text.return_value = " Intro \n\n1\n"
    page2 = Mock()
    page2.extract_text.return_value = "Body paragraph\n\n2"
    reader = Mock(is_encrypted=False, pages=[page1, page2])

    with patch("backend.utils.pdf_parser.PdfReader", return_value=reader):
        result = _extract_text_from_bytes(b"fake-pdf")

    assert result == "Intro\nBody paragraph"


def test_extract_text_from_bytes_skips_page_with_extraction_error() -> None:
    bad_page = Mock()
    bad_page.extract_text.side_effect = ValueError("cannot parse page")
    good_page = Mock()
    good_page.extract_text.return_value = "Useful content"
    reader = Mock(is_encrypted=False, pages=[bad_page, good_page])

    with patch("backend.utils.pdf_parser.PdfReader", return_value=reader):
        result = _extract_text_from_bytes(b"fake-pdf")

    assert result == "Useful content"


def test_extract_text_from_bytes_raises_for_encrypted_pdf() -> None:
    reader = Mock(is_encrypted=True, pages=[])

    with patch("backend.utils.pdf_parser.PdfReader", return_value=reader):
        with pytest.raises(PDFParseError, match="PDF is encrypted"):
            _extract_text_from_bytes(b"fake-pdf")


def test_extract_text_from_bytes_raises_for_empty_text() -> None:
    page = Mock()
    page.extract_text.return_value = ""
    reader = Mock(is_encrypted=False, pages=[page])

    with patch("backend.utils.pdf_parser.PdfReader", return_value=reader):
        with pytest.raises(PDFParseError, match="No text extracted"):
            _extract_text_from_bytes(b"fake-pdf")


def test_extract_text_from_bytes_wraps_corrupted_pdf_error() -> None:
    with patch("backend.utils.pdf_parser.PdfReader", side_effect=ValueError("corrupted pdf")):
        with pytest.raises(PDFParseError, match="PDF parsing error: corrupted pdf"):
            _extract_text_from_bytes(b"bad-data")


async def test_extract_text_from_url_success() -> None:
    pdf_data = b"url-pdf-bytes"
    response = AsyncMock()
    response.read.return_value = pdf_data
    response.raise_for_status = Mock()

    class _ContextManager:
        async def __aenter__(self):
            return response

        async def __aexit__(self, exc_type, exc, tb):
            return False

    session = Mock()
    session.get.return_value = _ContextManager()

    with (
        patch("backend.utils.pdf_parser.get_session", new=AsyncMock(return_value=session)),
        patch(
            "backend.utils.pdf_parser._extract_text_from_bytes", return_value="parsed text"
        ) as extract,
    ):
        text = await extract_text_from_url("https://example.com/paper.pdf")

    assert text == "parsed text"
    session.get.assert_called_once_with(
        "https://example.com/paper.pdf", timeout=PDF_EXTRACTION_TIMEOUT
    )
    response.raise_for_status.assert_called_once()
    extract.assert_called_once_with(pdf_data)


async def test_extract_text_from_url_http_error_raises_pdf_parse_error() -> None:
    response = Mock()
    response.raise_for_status.side_effect = RuntimeError("404")

    class _ContextManager:
        async def __aenter__(self):
            return response

        async def __aexit__(self, exc_type, exc, tb):
            return False

    session = Mock()
    session.get.return_value = _ContextManager()

    with patch("backend.utils.pdf_parser.get_session", new=AsyncMock(return_value=session)):
        with pytest.raises(PDFParseError, match="Failed to extract text from URL"):
            await extract_text_from_url("https://example.com/missing.pdf")


async def test_extract_text_from_url_extraction_error_raises_pdf_parse_error() -> None:
    response = AsyncMock()
    response.read.return_value = b"pdf-bytes"
    response.raise_for_status = Mock()

    class _ContextManager:
        async def __aenter__(self):
            return response

        async def __aexit__(self, exc_type, exc, tb):
            return False

    session = Mock()
    session.get.return_value = _ContextManager()

    with (
        patch("backend.utils.pdf_parser.get_session", new=AsyncMock(return_value=session)),
        patch(
            "backend.utils.pdf_parser._extract_text_from_bytes",
            side_effect=PDFParseError("bad pdf"),
        ),
    ):
        with pytest.raises(PDFParseError, match="Failed to extract text from URL"):
            await extract_text_from_url("https://example.com/bad.pdf")


async def test_extract_text_from_minio_success() -> None:
    response = Mock()
    response.read.return_value = b"minio-pdf-bytes"
    response.close.return_value = None
    response.release_conn.return_value = None
    minio_client = Mock()
    minio_client.get_object.return_value = response

    with patch(
        "backend.utils.pdf_parser._extract_text_from_bytes", return_value="minio text"
    ) as extract:
        text = await extract_text_from_minio(minio_client, "papers", "a.pdf")

    assert text == "minio text"
    minio_client.get_object.assert_called_once_with("papers", "a.pdf")
    response.read.assert_called_once()
    response.close.assert_called_once()
    response.release_conn.assert_called_once()
    extract.assert_called_once_with(b"minio-pdf-bytes")


async def test_extract_text_from_minio_failure_raises_pdf_parse_error() -> None:
    minio_client = Mock()
    minio_client.get_object.side_effect = RuntimeError("object not found")

    with pytest.raises(PDFParseError, match="Failed to extract text from MinIO"):
        await extract_text_from_minio(minio_client, "papers", "missing.pdf")
