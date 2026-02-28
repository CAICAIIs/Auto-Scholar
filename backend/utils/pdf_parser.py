"""PDF text extraction utilities for academic papers.

This module provides async functions to extract text from PDF files stored in MinIO
or from URLs. It handles encrypted PDFs, corrupted files, and text cleaning.
"""

import asyncio
import logging
import tempfile
from pathlib import Path

from minio import Minio
from pypdf import PdfReader

from backend.constants import PDF_EXTRACTION_TIMEOUT
from backend.utils.http_pool import get_session

logger = logging.getLogger(__name__)


class PDFParseError(Exception):
    """Raised when PDF parsing fails."""

    pass


async def extract_text_from_minio(minio_client: Minio, bucket: str, object_key: str) -> str:
    """Extract text from a PDF stored in MinIO.

    Args:
        minio_client: MinIO client instance
        bucket: Bucket name
        object_key: Object key (path) in the bucket

    Returns:
        Extracted and cleaned text from the PDF

    Raises:
        PDFParseError: If PDF extraction fails
    """
    logger.info("Extracting text from MinIO: bucket=%s, key=%s", bucket, object_key)

    try:
        # Get PDF from MinIO (sync operation, wrap in thread)
        response = await asyncio.to_thread(minio_client.get_object, bucket, object_key)

        # Read PDF data
        pdf_data = await asyncio.to_thread(response.read)
        await asyncio.to_thread(response.close)
        await asyncio.to_thread(response.release_conn)

        # Extract text using pypdf
        text = await asyncio.to_thread(_extract_text_from_bytes, pdf_data)

        logger.info(
            "Text extracted from MinIO: key=%s, length=%d chars",
            object_key,
            len(text),
        )
        return text

    except Exception as e:
        logger.error(
            "PDF extraction failed from MinIO: bucket=%s, key=%s, error=%s",
            bucket,
            object_key,
            str(e),
        )
        raise PDFParseError(f"Failed to extract text from MinIO: {e}") from e


async def extract_text_from_url(pdf_url: str) -> str:
    """Extract text from a PDF at a given URL.

    Args:
        pdf_url: URL of the PDF file

    Returns:
        Extracted and cleaned text from the PDF

    Raises:
        PDFParseError: If PDF download or extraction fails
    """
    logger.info("Extracting text from URL: %s", pdf_url[:100])

    try:
        # Download PDF to temporary file
        session = await get_session()
        async with session.get(pdf_url, timeout=PDF_EXTRACTION_TIMEOUT) as response:
            response.raise_for_status()
            pdf_data = await response.read()

        # Extract text
        text = await asyncio.to_thread(_extract_text_from_bytes, pdf_data)

        logger.info(
            "Text extracted from URL: url=%s, length=%d chars",
            pdf_url[:50],
            len(text),
        )
        return text

    except Exception as e:
        logger.error(
            "PDF extraction failed from URL: url=%s, error=%s",
            pdf_url[:50],
            str(e),
        )
        raise PDFParseError(f"Failed to extract text from URL: {e}") from e


def _extract_text_from_bytes(pdf_data: bytes) -> str:
    """Extract text from PDF bytes.

    Args:
        pdf_data: PDF file content as bytes

    Returns:
        Extracted and cleaned text

    Raises:
        PDFParseError: If PDF is encrypted, corrupted, or empty
    """
    try:
        with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as tmp:
            tmp.write(pdf_data)
            tmp_path = tmp.name

        try:
            reader = PdfReader(tmp_path)

            if reader.is_encrypted:
                raise PDFParseError("PDF is encrypted")

            text_parts = []
            for page_num, page in enumerate(reader.pages, 1):
                try:
                    page_text = page.extract_text()
                    if page_text:
                        text_parts.append(page_text)
                except Exception as e:
                    logger.warning("Failed to extract text from page %d: %s", page_num, str(e))
                    continue

            if not text_parts:
                raise PDFParseError("No text extracted from PDF (may be scanned image)")

            full_text = "\n\n".join(text_parts)
            cleaned_text = _clean_text(full_text)

            return cleaned_text

        finally:
            Path(tmp_path).unlink(missing_ok=True)

    except PDFParseError:
        raise
    except Exception as e:
        raise PDFParseError(f"PDF parsing error: {e}") from e


def _extract_text_with_pages(pdf_data: bytes) -> list[tuple[int, str]]:
    """Extract text from PDF bytes with page numbers.

    Args:
        pdf_data: PDF file content as bytes

    Returns:
        List of (page_number, cleaned_text) tuples

    Raises:
        PDFParseError: If PDF is encrypted, corrupted, or empty
    """
    try:
        with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as tmp:
            tmp.write(pdf_data)
            tmp_path = tmp.name

        try:
            reader = PdfReader(tmp_path)

            if reader.is_encrypted:
                raise PDFParseError("PDF is encrypted")

            page_texts = []
            for page_num, page in enumerate(reader.pages, 1):
                try:
                    page_text = page.extract_text()
                    if page_text:
                        cleaned_page_text = _clean_text(page_text)
                        if cleaned_page_text.strip():
                            page_texts.append((page_num, cleaned_page_text))
                except Exception as e:
                    logger.warning("Failed to extract text from page %d: %s", page_num, str(e))
                    continue

            if not page_texts:
                raise PDFParseError("No text extracted from PDF (may be scanned image)")

            return page_texts

        finally:
            Path(tmp_path).unlink(missing_ok=True)

    except PDFParseError:
        raise
    except Exception as e:
        raise PDFParseError(f"PDF parsing error: {e}") from e


def _clean_text(text: str) -> str:
    """Clean extracted PDF text.

    Args:
        text: Raw extracted text

    Returns:
        Cleaned text with normalized whitespace and line breaks
    """
    # Remove excessive whitespace
    lines = text.split("\n")
    cleaned_lines = []

    for line in lines:
        # Strip whitespace
        line = line.strip()

        # Skip empty lines
        if not line:
            continue

        # Skip likely page numbers (single number on a line)
        if line.isdigit() and len(line) <= 4:
            continue

        # Skip common headers/footers (heuristic)
        if len(line) < 5 and not line[0].isalnum():
            continue

        cleaned_lines.append(line)

    # Join with single newline, then normalize paragraph breaks
    text = "\n".join(cleaned_lines)

    # Normalize multiple newlines to double newline (paragraph break)
    while "\n\n\n" in text:
        text = text.replace("\n\n\n", "\n\n")

    return text.strip()
