import asyncio
import logging
import os
import re
from typing import Any

import aiohttp
from tenacity import retry, wait_exponential, stop_after_attempt, retry_if_exception_type

from app.schemas import PaperMetadata

logger = logging.getLogger(__name__)

UNPAYWALL_BASE = "https://api.unpaywall.org/v2"
OPENALEX_BASE = "https://api.openalex.org"


class FullTextAPIError(Exception):
    pass


def _normalize_doi(doi: str) -> str:
    doi = doi.strip()
    doi = re.sub(r"^https?://(dx\.)?doi\.org/", "", doi, flags=re.I)
    return doi.lower()


@retry(
    wait=wait_exponential(multiplier=1, min=1, max=5),
    stop=stop_after_attempt(3),
    retry=retry_if_exception_type(aiohttp.ClientError),
)
async def _fetch_json(
    session: aiohttp.ClientSession,
    url: str,
    params: dict[str, Any] | None = None,
) -> dict[str, Any] | None:
    async with session.get(url, params=params) as resp:
        if resp.status == 404:
            return None
        if resp.status == 429:
            await asyncio.sleep(2)
            raise aiohttp.ClientError("Rate limited")
        if resp.status != 200:
            return None
        return await resp.json()


def _extract_pdf_from_unpaywall(data: dict[str, Any]) -> str | None:
    best = data.get("best_oa_location") or {}
    if best.get("pdf_url"):
        return best["pdf_url"]

    for loc in data.get("oa_locations", []) or []:
        if loc.get("pdf_url"):
            return loc["pdf_url"]
    return None


def _extract_pdf_from_openalex(work: dict[str, Any]) -> str | None:
    oa = work.get("open_access") or {}
    oa_url = oa.get("oa_url")
    if oa_url and str(oa_url).lower().endswith(".pdf"):
        return oa_url

    best = work.get("best_oa_location") or {}
    if best.get("pdf_url"):
        return best["pdf_url"]

    primary = work.get("primary_location") or {}
    if primary.get("pdf_url"):
        return primary["pdf_url"]

    for loc in work.get("locations", []) or []:
        if loc.get("pdf_url"):
            return loc["pdf_url"]

    return None


def _extract_doi_from_openalex(work: dict[str, Any]) -> str | None:
    doi = work.get("doi")
    if doi:
        return _normalize_doi(doi)
    
    ids = work.get("ids") or {}
    if ids.get("doi"):
        return _normalize_doi(ids["doi"])
    return None


async def _unpaywall_lookup(
    session: aiohttp.ClientSession,
    doi: str,
    email: str,
) -> dict[str, Any] | None:
    doi = _normalize_doi(doi)
    url = f"{UNPAYWALL_BASE}/{doi}"
    return await _fetch_json(session, url, params={"email": email})


async def _openalex_lookup_by_doi(
    session: aiohttp.ClientSession,
    doi: str,
) -> dict[str, Any] | None:
    doi = _normalize_doi(doi)
    url = f"{OPENALEX_BASE}/works/https://doi.org/{doi}"
    return await _fetch_json(session, url)


async def _openalex_search_by_title(
    session: aiohttp.ClientSession,
    title: str,
    year: int | None = None,
) -> list[dict[str, Any]]:
    url = f"{OPENALEX_BASE}/works"
    params: dict[str, Any] = {"search": title, "per-page": 5}
    if year:
        params["filter"] = f"publication_year:{year}"
    
    data = await _fetch_json(session, url, params=params)
    if not data:
        return []
    return data.get("results", []) or []


async def resolve_pdf_url(
    title: str,
    doi: str | None = None,
    year: int | None = None,
) -> tuple[str | None, str | None]:
    email = os.environ.get("UNPAYWALL_EMAIL", "auto-scholar@example.com")
    
    timeout = aiohttp.ClientTimeout(total=20)
    headers = {"User-Agent": "auto-scholar/1.0"}

    async with aiohttp.ClientSession(timeout=timeout, headers=headers) as session:
        resolved_doi = doi
        pdf_url = None

        if doi:
            up = await _unpaywall_lookup(session, doi, email)
            if up:
                pdf_url = _extract_pdf_from_unpaywall(up)
                if pdf_url:
                    logger.debug("Found PDF via Unpaywall for DOI %s", doi)
                    return pdf_url, resolved_doi

            ox = await _openalex_lookup_by_doi(session, doi)
            if ox:
                pdf_url = _extract_pdf_from_openalex(ox)
                if pdf_url:
                    logger.debug("Found PDF via OpenAlex DOI lookup for %s", doi)
                    return pdf_url, resolved_doi

        candidates = await _openalex_search_by_title(session, title, year)
        for work in candidates:
            work_title = work.get("title", "").lower()
            if title.lower() in work_title or work_title in title.lower():
                pdf_url = _extract_pdf_from_openalex(work)
                if not resolved_doi:
                    resolved_doi = _extract_doi_from_openalex(work)
                if pdf_url:
                    logger.debug("Found PDF via OpenAlex title search for '%s'", title[:50])
                    return pdf_url, resolved_doi

    return None, resolved_doi


async def enrich_paper_with_fulltext(paper: PaperMetadata) -> PaperMetadata:
    if paper.pdf_url:
        return paper

    pdf_url, doi = await resolve_pdf_url(
        title=paper.title,
        doi=paper.doi,
        year=paper.year,
    )

    updates: dict[str, Any] = {}
    if pdf_url:
        updates["pdf_url"] = pdf_url
    if doi and not paper.doi:
        updates["doi"] = doi

    if updates:
        return paper.model_copy(update=updates)
    return paper


async def enrich_papers_with_fulltext(
    papers: list[PaperMetadata],
    concurrency: int = 3,
) -> list[PaperMetadata]:
    semaphore = asyncio.Semaphore(concurrency)

    async def enrich_with_limit(paper: PaperMetadata) -> PaperMetadata:
        async with semaphore:
            try:
                return await enrich_paper_with_fulltext(paper)
            except Exception as e:
                logger.warning("Failed to enrich paper '%s': %s", paper.title[:50], e)
                return paper

    tasks = [enrich_with_limit(p) for p in papers]
    return await asyncio.gather(*tasks)
