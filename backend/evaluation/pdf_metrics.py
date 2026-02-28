"""PDF download metrics tracking for observability."""

from dataclasses import dataclass
from datetime import UTC, datetime


@dataclass
class PDFDownloadMetric:
    """Record of a single PDF download attempt."""

    paper_id: str
    pdf_url: str
    is_cached: bool
    size_bytes: int | None
    duration_ms: float
    success: bool
    error: str | None
    timestamp: datetime


# Module-level storage (in-memory for current session)
_pdf_downloads: list[PDFDownloadMetric] = []


def record_pdf_download(
    paper_id: str,
    pdf_url: str,
    is_cached: bool,
    size_bytes: int | None,
    duration_ms: float,
    success: bool,
    error: str | None = None,
) -> None:
    """Record a PDF download attempt."""
    _pdf_downloads.append(
        PDFDownloadMetric(
            paper_id=paper_id,
            pdf_url=pdf_url,
            is_cached=is_cached,
            size_bytes=size_bytes,
            duration_ms=duration_ms,
            success=success,
            error=error,
            timestamp=datetime.now(UTC),
        )
    )


def get_pdf_metrics() -> list[PDFDownloadMetric]:
    """Get all recorded PDF download metrics."""
    return _pdf_downloads.copy()


def get_pdf_stats() -> dict[str, any]:
    """Get aggregate PDF download statistics."""
    if not _pdf_downloads:
        return {}

    total = len(_pdf_downloads)
    cached = sum(1 for m in _pdf_downloads if m.is_cached)
    successful = sum(1 for m in _pdf_downloads if m.success)
    failed = total - successful

    successful_downloads = [m for m in _pdf_downloads if m.success and m.size_bytes]
    total_bytes = sum(m.size_bytes for m in successful_downloads)
    avg_size = total_bytes / len(successful_downloads) if successful_downloads else 0

    durations = [m.duration_ms for m in _pdf_downloads if m.success]
    avg_duration = sum(durations) / len(durations) if durations else 0

    return {
        "total_attempts": total,
        "cache_hits": cached,
        "cache_hit_rate": cached / total if total > 0 else 0,
        "successful": successful,
        "failed": failed,
        "success_rate": successful / total if total > 0 else 0,
        "total_bytes_downloaded": total_bytes,
        "avg_size_bytes": avg_size,
        "avg_duration_ms": avg_duration,
    }


def reset_pdf_metrics() -> None:
    """Reset all PDF metrics (for testing)."""
    _pdf_downloads.clear()
