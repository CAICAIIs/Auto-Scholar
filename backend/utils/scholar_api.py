import asyncio
import logging
import os
import time
import xml.etree.ElementTree as ET
from typing import Any

import aiohttp
from dotenv import load_dotenv
from tenacity import retry, retry_if_exception_type, stop_after_attempt, wait_exponential

from backend.evaluation.cost_tracker import record_search_call
from backend.schemas import PaperMetadata, PaperSource, ResearchPlan
from backend.utils.http_pool import get_session
from backend.utils.source_tracker import record_failure, record_success, should_skip

load_dotenv()

logger = logging.getLogger(__name__)


SEMANTIC_SCHOLAR_SEARCH_URL = "https://api.semanticscholar.org/graph/v1/paper/search"
ARXIV_SEARCH_URL = "http://export.arxiv.org/api/query"
PUBMED_ESEARCH_URL = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esearch.fcgi"
PUBMED_ESUMMARY_URL = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esummary.fcgi"

FIELDS = "paperId,title,authors,abstract,url,year,externalIds,openAccessPdf"


class ScholarAPIError(Exception):
    pass


class RateLimitError(ScholarAPIError):
    pass


class ArxivAPIError(Exception):
    pass


class PubMedAPIError(Exception):
    pass


@retry(
    wait=wait_exponential(multiplier=1, min=2, max=10),
    stop=stop_after_attempt(2),
    retry=retry_if_exception_type(aiohttp.ClientError),
)
async def _fetch_semantic_scholar(
    session: aiohttp.ClientSession,
    query: str,
    limit: int,
    offset: int,
) -> dict[str, Any]:
    headers: dict[str, str] = {"Accept": "application/json"}
    api_key = os.environ.get("SEMANTIC_SCHOLAR_API_KEY")
    if api_key:
        headers["x-api-key"] = api_key

    params: dict[str, str | int] = {
        "query": query,
        "limit": limit,
        "offset": offset,
        "fields": FIELDS,
    }

    async with session.get(SEMANTIC_SCHOLAR_SEARCH_URL, headers=headers, params=params) as resp:
        if resp.status == 429:
            logger.warning("Rate limited by Semantic Scholar for query '%s'", query[:50])
            raise RateLimitError("429 Too Many Requests")
        if resp.status != 200:
            text = await resp.text()
            raise ScholarAPIError(f"Semantic Scholar API error {resp.status}: {text}")
        return await resp.json()


def _parse_semantic_scholar_paper(raw: dict[str, Any]) -> PaperMetadata:
    authors: list[str] = [a.get("name", "Unknown") for a in raw.get("authors", [])]

    external_ids = raw.get("externalIds") or {}
    doi = external_ids.get("DOI")

    open_access_pdf = raw.get("openAccessPdf") or {}
    pdf_url = open_access_pdf.get("url")

    return PaperMetadata(
        paper_id=raw.get("paperId", ""),
        title=raw.get("title", ""),
        authors=authors,
        abstract=raw.get("abstract", "") or "",
        url=raw.get("url", "") or "",
        year=raw.get("year"),
        doi=doi,
        pdf_url=pdf_url,
        source=PaperSource.SEMANTIC_SCHOLAR,
    )


@retry(
    wait=wait_exponential(multiplier=1, min=1, max=5),
    stop=stop_after_attempt(3),
    retry=retry_if_exception_type(aiohttp.ClientError),
)
async def _fetch_arxiv(
    session: aiohttp.ClientSession,
    query: str,
    limit: int,
) -> str:
    params: dict[str, str | int] = {
        "search_query": f"all:{query}",
        "start": 0,
        "max_results": limit,
        "sortBy": "relevance",
        "sortOrder": "descending",
    }

    async with session.get(ARXIV_SEARCH_URL, params=params) as resp:
        if resp.status != 200:
            text = await resp.text()
            raise ArxivAPIError(f"arXiv API error {resp.status}: {text}")
        return await resp.text()


def _parse_arxiv_papers(xml_content: str) -> list[PaperMetadata]:
    papers: list[PaperMetadata] = []

    root = ET.fromstring(xml_content)
    ns = {"atom": "http://www.w3.org/2005/Atom"}

    for entry in root.findall("atom:entry", ns):
        arxiv_id_elem = entry.find("atom:id", ns)
        arxiv_id = arxiv_id_elem.text if arxiv_id_elem is not None else ""
        paper_id = arxiv_id.split("/abs/")[-1] if arxiv_id else ""

        title_elem = entry.find("atom:title", ns)
        title = (
            title_elem.text.strip().replace("\n", " ")
            if title_elem is not None and title_elem.text
            else ""
        )

        abstract_elem = entry.find("atom:summary", ns)
        abstract = (
            abstract_elem.text.strip().replace("\n", " ")
            if abstract_elem is not None and abstract_elem.text
            else ""
        )

        authors: list[str] = []
        for author in entry.findall("atom:author", ns):
            name_elem = author.find("atom:name", ns)
            if name_elem is not None and name_elem.text:
                authors.append(name_elem.text)

        published_elem = entry.find("atom:published", ns)
        year = None
        if published_elem is not None and published_elem.text:
            year = int(published_elem.text[:4])

        link_elem = entry.find("atom:id", ns)
        url = link_elem.text if link_elem is not None and link_elem.text else ""

        pdf_url = None
        for link in entry.findall("atom:link", ns):
            if link.get("title") == "pdf":
                pdf_url = link.get("href")
                break

        arxiv_doi = f"10.48550/arXiv.{paper_id}" if paper_id else None

        if paper_id and title:
            papers.append(
                PaperMetadata(
                    paper_id=f"arxiv:{paper_id}",
                    title=title,
                    authors=authors,
                    abstract=abstract,
                    url=url,
                    year=year,
                    doi=arxiv_doi,
                    pdf_url=pdf_url,
                    source=PaperSource.ARXIV,
                )
            )

    return papers


@retry(
    wait=wait_exponential(multiplier=1, min=1, max=5),
    stop=stop_after_attempt(3),
    retry=retry_if_exception_type(aiohttp.ClientError),
)
async def _fetch_pubmed_ids(
    session: aiohttp.ClientSession,
    query: str,
    limit: int,
) -> list[str]:
    params: dict[str, str | int] = {
        "db": "pubmed",
        "term": query,
        "retmax": limit,
        "retmode": "json",
        "sort": "relevance",
    }

    api_key = os.environ.get("PUBMED_API_KEY")
    if api_key:
        params["api_key"] = api_key

    async with session.get(PUBMED_ESEARCH_URL, params=params) as resp:
        if resp.status != 200:
            text = await resp.text()
            raise PubMedAPIError(f"PubMed ESearch error {resp.status}: {text}")
        data = await resp.json()
        return data.get("esearchresult", {}).get("idlist", [])


@retry(
    wait=wait_exponential(multiplier=1, min=1, max=5),
    stop=stop_after_attempt(3),
    retry=retry_if_exception_type(aiohttp.ClientError),
)
async def _fetch_pubmed_summaries(
    session: aiohttp.ClientSession,
    pmids: list[str],
) -> dict[str, Any]:
    if not pmids:
        return {}

    params = {
        "db": "pubmed",
        "id": ",".join(pmids),
        "retmode": "json",
    }

    api_key = os.environ.get("PUBMED_API_KEY")
    if api_key:
        params["api_key"] = api_key

    async with session.get(PUBMED_ESUMMARY_URL, params=params) as resp:
        if resp.status != 200:
            text = await resp.text()
            raise PubMedAPIError(f"PubMed ESummary error {resp.status}: {text}")
        return await resp.json()


def _parse_pubmed_papers(summary_data: dict[str, Any], pmids: list[str]) -> list[PaperMetadata]:
    papers: list[PaperMetadata] = []
    result = summary_data.get("result", {})

    for pmid in pmids:
        if pmid not in result:
            continue

        doc = result[pmid]
        if not isinstance(doc, dict):
            continue

        title = doc.get("title", "")

        authors: list[str] = []
        for author in doc.get("authors", []):
            if isinstance(author, dict) and "name" in author:
                authors.append(author["name"])

        year = None
        pubdate = doc.get("pubdate", "")
        if pubdate and len(pubdate) >= 4:
            try:
                year = int(pubdate[:4])
            except ValueError:
                pass

        doi = None
        elocationid = doc.get("elocationid", "")
        if elocationid and elocationid.startswith("doi:"):
            doi = elocationid[4:].strip()

        articleids = doc.get("articleids", [])
        for aid in articleids:
            if isinstance(aid, dict) and aid.get("idtype") == "doi":
                doi = aid.get("value")
                break

        url = f"https://pubmed.ncbi.nlm.nih.gov/{pmid}/"

        if title:
            papers.append(
                PaperMetadata(
                    paper_id=f"pubmed:{pmid}",
                    title=title,
                    authors=authors,
                    abstract="",
                    url=url,
                    year=year,
                    doi=doi,
                    source=PaperSource.PUBMED,
                )
            )

    return papers


async def search_semantic_scholar(
    queries: list[str],
    limit_per_query: int = 10,
) -> list[PaperMetadata]:
    session = await get_session()
    has_api_key = bool(os.environ.get("SEMANTIC_SCHOLAR_API_KEY"))
    concurrency = 3 if has_api_key else 2
    semaphore = asyncio.Semaphore(concurrency)
    rate_limited = False

    async def fetch_with_limit(query: str) -> list[PaperMetadata]:
        nonlocal rate_limited
        if rate_limited:
            return []

        async with semaphore:
            try:
                result = await _fetch_semantic_scholar(
                    session, query, limit=limit_per_query, offset=0
                )
                record_search_call("semantic_scholar")
                return [
                    _parse_semantic_scholar_paper(raw)
                    for raw in result.get("data", [])
                    if raw.get("paperId")
                ]
            except RateLimitError:
                rate_limited = True
                logger.warning("Semantic Scholar rate limited, skipping remaining queries")
                return []
            except Exception as e:
                logger.error("Semantic Scholar search failed for '%s': %s", query, e)
                return []

    results = await asyncio.gather(*[fetch_with_limit(q) for q in queries])

    papers: list[PaperMetadata] = []
    seen_ids: set[str] = set()
    for paper_list in results:
        for paper in paper_list:
            if paper.paper_id not in seen_ids:
                seen_ids.add(paper.paper_id)
                papers.append(paper)

    return papers


async def search_arxiv(
    queries: list[str],
    limit_per_query: int = 10,
) -> list[PaperMetadata]:
    session = await get_session()
    tasks = [_fetch_arxiv(session, q, limit=limit_per_query) for q in queries]
    results = await asyncio.gather(*tasks, return_exceptions=True)

    papers: list[PaperMetadata] = []
    seen_ids: set[str] = set()
    for r in results:
        if isinstance(r, BaseException):
            logger.error("arXiv search failed: %s", r)
            continue
        record_search_call("arxiv")
        for paper in _parse_arxiv_papers(r):
            if paper.paper_id and paper.paper_id not in seen_ids:
                seen_ids.add(paper.paper_id)
                papers.append(paper)
    return papers


async def search_pubmed(
    queries: list[str],
    limit_per_query: int = 10,
) -> list[PaperMetadata]:
    session = await get_session()
    id_tasks = [_fetch_pubmed_ids(session, q, limit=limit_per_query) for q in queries]
    id_results = await asyncio.gather(*id_tasks, return_exceptions=True)

    all_pmids: list[str] = []
    seen_pmids: set[str] = set()
    for r in id_results:
        if isinstance(r, BaseException):
            logger.error("PubMed ID search failed: %s", r)
            continue
        record_search_call("pubmed")
        for pmid in r:
            if pmid not in seen_pmids:
                seen_pmids.add(pmid)
                all_pmids.append(pmid)

    if not all_pmids:
        return []

    summary_data = await _fetch_pubmed_summaries(session, all_pmids)
    return _parse_pubmed_papers(summary_data, all_pmids)


def deduplicate_papers(papers: list[PaperMetadata]) -> list[PaperMetadata]:
    seen_titles: dict[str, PaperMetadata] = {}
    seen_ids: set[str] = set()
    result: list[PaperMetadata] = []

    for paper in papers:
        if paper.paper_id in seen_ids:
            continue
        seen_ids.add(paper.paper_id)

        normalized_title = paper.title.lower().strip()
        normalized_title = "".join(c for c in normalized_title if c.isalnum() or c.isspace())
        normalized_title = " ".join(normalized_title.split())

        if normalized_title in seen_titles:
            existing = seen_titles[normalized_title]
            if paper.source == PaperSource.SEMANTIC_SCHOLAR:
                seen_titles[normalized_title] = paper
                result = [p for p in result if p.paper_id != existing.paper_id]
                result.append(paper)
            continue

        seen_titles[normalized_title] = paper
        result.append(paper)

    return result


async def search_papers_multi_source(
    queries: list[str],
    sources: list[PaperSource] | None = None,
    limit_per_query: int = 10,
) -> list[PaperMetadata]:
    if sources is None:
        sources = [PaperSource.SEMANTIC_SCHOLAR]

    all_papers: list[PaperMetadata] = []

    tasks = []
    source_names = []
    source_keys = []

    if PaperSource.SEMANTIC_SCHOLAR in sources:
        if should_skip("semantic_scholar"):
            logger.warning("Skipping Semantic Scholar due to recent failures")
        else:
            tasks.append(search_semantic_scholar(queries, limit_per_query))
            source_names.append("Semantic Scholar")
            source_keys.append("semantic_scholar")

    if PaperSource.ARXIV in sources:
        if should_skip("arxiv"):
            logger.warning("Skipping arXiv due to recent failures")
        else:
            tasks.append(search_arxiv(queries, limit_per_query))
            source_names.append("arXiv")
            source_keys.append("arxiv")

    if PaperSource.PUBMED in sources:
        if should_skip("pubmed"):
            logger.warning("Skipping PubMed due to recent failures")
        else:
            tasks.append(search_pubmed(queries, limit_per_query))
            source_names.append("PubMed")
            source_keys.append("pubmed")

    if not tasks:
        return []

    logger.info("Starting parallel search across %s", source_names)
    start_time = time.perf_counter()
    results = await asyncio.gather(*tasks, return_exceptions=True)
    elapsed = time.perf_counter() - start_time
    logger.info("All source searches completed in %.2fs", elapsed)

    for i, r in enumerate(results):
        if isinstance(r, BaseException):
            logger.error("Search from %s failed: %s", source_names[i], r)
            record_failure(source_keys[i])
            continue
        logger.info("Search from %s returned %d papers", source_names[i], len(r))
        record_success(source_keys[i])
        all_papers.extend(r)

    return deduplicate_papers(all_papers)


async def search_by_plan(
    plan: ResearchPlan,
    default_limit: int = 10,
    allowed_sources: list[PaperSource] | None = None,
) -> list[PaperMetadata]:
    """Search papers per sub-question, ensuring all allowed sources are queried.

    1. Each sub-question searches its preferred_source (if allowed).
    2. Sources in allowed_sources that no sub-question covers get supplemental
       searches using all collected keywords, so every user-selected source
       contributes results.
    """
    if not plan.sub_questions:
        return []

    source_dispatch = {
        PaperSource.SEMANTIC_SCHOLAR: search_semantic_scholar,
        PaperSource.ARXIV: search_arxiv,
        PaperSource.PUBMED: search_pubmed,
    }

    tasks: list[Any] = []
    task_labels: list[str] = []
    used_sources: set[PaperSource] = set()

    all_keywords: list[str] = []
    for sq in plan.sub_questions:
        all_keywords.extend(sq.keywords)

    for sq in plan.sub_questions:
        source = sq.preferred_source
        if allowed_sources and source not in allowed_sources:
            source = allowed_sources[0]
        limit = sq.estimated_papers or default_limit

        if should_skip(source.value):
            logger.warning(
                "search_by_plan: skipping %s for sub-question '%s' due to recent failures",
                source.value,
                sq.question[:60],
            )
            continue

        search_fn = source_dispatch.get(source)
        if search_fn is None:
            logger.warning("search_by_plan: unknown source %s, skipping", source)
            continue

        used_sources.add(source)
        tasks.append(search_fn(sq.keywords, limit_per_query=limit))
        task_labels.append(f"{sq.question[:40]}→{source.value}")

    if allowed_sources and all_keywords:
        unique_keywords = list(dict.fromkeys(all_keywords))
        for source in allowed_sources:
            if source in used_sources:
                continue
            if should_skip(source.value):
                logger.warning(
                    "search_by_plan: skipping supplemental %s due to recent failures",
                    source.value,
                )
                continue
            search_fn = source_dispatch.get(source)
            if search_fn is None:
                continue
            used_sources.add(source)
            tasks.append(search_fn(unique_keywords, limit_per_query=default_limit))
            task_labels.append(f"supplemental→{source.value}")

    if not tasks:
        return []

    logger.info(
        "search_by_plan: launching %d searches (sources: %s): %s",
        len(tasks),
        [s.value for s in used_sources],
        task_labels,
    )
    start_time = time.perf_counter()
    results = await asyncio.gather(*tasks, return_exceptions=True)
    elapsed = time.perf_counter() - start_time
    logger.info("search_by_plan: all searches completed in %.2fs", elapsed)

    all_papers: list[PaperMetadata] = []
    for i, r in enumerate(results):
        if isinstance(r, BaseException):
            logger.error("search_by_plan: search for '%s' failed: %s", task_labels[i], r)
            continue
        logger.info("search_by_plan: '%s' returned %d papers", task_labels[i], len(r))
        all_papers.extend(r)

    return deduplicate_papers(all_papers)


async def search_papers(query: str, limit: int = 10) -> list[PaperMetadata]:
    return await search_semantic_scholar([query], limit_per_query=limit)


async def search_papers_batch(queries: list[str], limit_per_query: int = 10) -> list[PaperMetadata]:
    return await search_semantic_scholar(queries, limit_per_query=limit_per_query)
