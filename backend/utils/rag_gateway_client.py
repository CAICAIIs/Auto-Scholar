import logging
import time
from typing import Any

import aiohttp

from backend.constants import RAG_GATEWAY_TIMEOUT, RAG_GATEWAY_URL
from backend.schemas import PaperMetadata

logger = logging.getLogger(__name__)

_CIRCUIT_COOLDOWN = 120.0
_circuit_open_until: float = 0.0


class GatewayError(Exception):
    pass


def _is_circuit_open() -> bool:
    return time.monotonic() < _circuit_open_until


def _trip_circuit() -> None:
    global _circuit_open_until
    _circuit_open_until = time.monotonic() + _CIRCUIT_COOLDOWN
    logger.warning("rag_gateway: circuit breaker tripped, skipping for %.0fs", _CIRCUIT_COOLDOWN)


def _reset_circuit() -> None:
    global _circuit_open_until
    _circuit_open_until = 0.0


async def submit_papers_to_gateway(
    papers: list[PaperMetadata],
) -> list[dict[str, Any]]:
    if not RAG_GATEWAY_URL:
        raise GatewayError("RAG_GATEWAY_URL not configured")

    if _is_circuit_open():
        raise GatewayError("circuit breaker open — gateway recently failed")

    items = []
    for p in papers:
        if p.pdf_url:
            items.append(
                {
                    "paper_id": p.paper_id,
                    "source_url": p.pdf_url,
                }
            )

    if not items:
        logger.info("rag_gateway: no papers with PDF URLs to submit")
        return []

    url = f"{RAG_GATEWAY_URL.rstrip('/')}/api/v1/ingest/batch"
    timeout = aiohttp.ClientTimeout(total=RAG_GATEWAY_TIMEOUT)

    try:
        async with aiohttp.ClientSession(timeout=timeout) as session:
            async with session.post(url, json={"items": items}) as resp:
                if resp.status == 207:
                    results = await resp.json()
                    submitted = sum(1 for r in results if r.get("status") == 202)
                    failed = len(results) - submitted
                    logger.info(
                        "rag_gateway: batch submitted — %d accepted, %d failed",
                        submitted,
                        failed,
                    )
                    _reset_circuit()
                    return results

                body = await resp.text()
                _trip_circuit()
                raise GatewayError(f"gateway returned {resp.status}: {body[:200]}")
    except aiohttp.ClientError as e:
        _trip_circuit()
        raise GatewayError(f"gateway connection failed: {e}") from e


async def check_gateway_health() -> bool:
    if not RAG_GATEWAY_URL:
        return False

    if _is_circuit_open():
        return False

    url = f"{RAG_GATEWAY_URL.rstrip('/')}/api/v1/health"
    timeout = aiohttp.ClientTimeout(total=3)

    try:
        async with aiohttp.ClientSession(timeout=timeout) as session:
            async with session.get(url) as resp:
                return resp.status == 200
    except Exception:
        return False
