"""PDF downloader with MinIO storage and Redis caching."""

import hashlib
import time
from typing import Any

from backend.evaluation.pdf_metrics import record_pdf_download
from backend.utils.logging import get_logger

logger = get_logger(__name__)


class PDFDownloader:
    """Download PDFs from URLs, store in MinIO, cache results in Redis."""

    def __init__(
        self,
        minio_client: Any | None = None,
        redis_client: Any | None = None,
        bucket_name: str = "papers",
    ) -> None:
        """Initialize PDF downloader.

        Args:
            minio_client: MinIO client instance
            redis_client: Redis client instance
            bucket_name: MinIO bucket name for PDF storage
        """
        self.minio_client = minio_client
        self.redis_client = redis_client
        self.bucket_name = bucket_name

    async def ensure_bucket_exists(self) -> None:
        """Ensure MinIO bucket exists, create if not."""
        if self.minio_client is None:
            logger.warning("PDF cache: MinIO client not available, skipping bucket check")
            return

        try:
            if not self.minio_client.bucket_exists(self.bucket_name):
                self.minio_client.make_bucket(self.bucket_name)
                logger.info("PDF cache: Created MinIO bucket: %s", self.bucket_name)
        except Exception as e:
            logger.error("PDF cache: Failed to ensure bucket exists: %s", str(e))
            raise

    def _get_content_hash(self, pdf_url: str) -> str:
        """Generate SHA256 hash of PDF URL for cache key."""
        return hashlib.sha256(pdf_url.encode()).hexdigest()

    def _get_cache_key(self, paper_id: str, content_hash: str) -> str:
        """Get Redis cache key for PDF metadata."""
        return f"pdf:{paper_id}:{content_hash[:16]}"

    def _get_object_key(self, paper_id: str, content_hash: str) -> str:
        """Get MinIO object key for PDF file."""
        return f"{paper_id}/{content_hash[:16]}.pdf"

    async def download_pdf(
        self,
        paper_id: str,
        pdf_url: str,
    ) -> tuple[bool, str | None, int | None]:
        """Download PDF, cache in Redis, store in MinIO.

        Args:
            paper_id: Paper identifier
            pdf_url: URL to download PDF from

        Returns:
            tuple of (is_cached, object_key, size_bytes)
        """
        start_time = time.perf_counter()
        content_hash = self._get_content_hash(pdf_url)
        cache_key = self._get_cache_key(paper_id, content_hash)
        object_key = self._get_object_key(paper_id, content_hash)

        # Check Redis cache
        if self.redis_client is not None:
            try:
                cached_meta = self.redis_client.get(cache_key)
                if cached_meta:
                    logger.info(
                        "PDF cache hit: paper_id=%s, hash=%s",
                        paper_id,
                        content_hash[:16],
                    )
                    duration_ms = (time.perf_counter() - start_time) * 1000
                    record_pdf_download(
                        paper_id=paper_id,
                        pdf_url=pdf_url,
                        is_cached=True,
                        size_bytes=None,
                        duration_ms=duration_ms,
                        success=True,
                        error=None,
                    )
                    return True, object_key, None  # Size not in cache metadata
            except Exception as e:
                logger.error("PDF cache: Redis lookup failed: %s", str(e))

        # Cache miss - download from URL
        logger.info(
            "PDF cache miss: paper_id=%s, starting download from %s",
            paper_id,
            pdf_url[:50],
        )
        logger.info("Downloading PDF: paper_id=%s, url=%s", paper_id, pdf_url)

        try:
            import aiohttp

            async with aiohttp.ClientSession() as session:
                async with session.get(pdf_url, timeout=30) as response:
                    if response.status != 200:
                        raise Exception(f"HTTP {response.status}")
                    pdf_content = await response.read()
                    size_bytes = len(pdf_content)

            logger.info(
                "PDF downloaded: paper_id=%s, size=%d bytes, object_key=%s",
                paper_id,
                size_bytes,
                object_key,
            )

            # Upload to MinIO
            if self.minio_client is not None:
                await self.ensure_bucket_exists()
                from io import BytesIO

                self.minio_client.put_object(
                    bucket_name=self.bucket_name,
                    object_name=object_key,
                    data=BytesIO(pdf_content),
                    length=size_bytes,
                    content_type="application/pdf",
                )
                logger.info(
                    "Uploading to MinIO: paper_id=%s, bucket=%s, key=%s",
                    paper_id,
                    self.bucket_name,
                    object_key,
                )

            # Cache metadata in Redis
            if self.redis_client is not None:
                import json

                metadata = {
                    "paper_id": paper_id,
                    "pdf_url": pdf_url,
                    "content_hash": content_hash,
                    "object_key": object_key,
                    "size_bytes": size_bytes,
                }
                self.redis_client.setex(
                    cache_key,
                    3600,  # 1 hour TTL
                    json.dumps(metadata),
                )

            duration_ms = (time.perf_counter() - start_time) * 1000
            logger.info(
                "PDF download complete: paper_id=%s, duration=%.0fms",
                paper_id,
                duration_ms,
            )

            record_pdf_download(
                paper_id=paper_id,
                pdf_url=pdf_url,
                is_cached=False,
                size_bytes=size_bytes,
                duration_ms=duration_ms,
                success=True,
                error=None,
            )

            return False, object_key, size_bytes

        except Exception as e:
            duration_ms = (time.perf_counter() - start_time) * 1000
            logger.error(
                "PDF download failed: paper_id=%s, url=%s, error=%s",
                paper_id,
                pdf_url,
                str(e),
            )
            record_pdf_download(
                paper_id=paper_id,
                pdf_url=pdf_url,
                is_cached=False,
                size_bytes=None,
                duration_ms=duration_ms,
                success=False,
                error=str(e),
            )
            raise
