import os
import asyncio
import logging
import xml.etree.ElementTree as ET
from typing import Any

import aiohttp
from tenacity import retry, wait_exponential, stop_after_attempt, retry_if_exception_type
from dotenv import load_dotenv

from app.schemas import PaperMetadata, PaperSource

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
    stop=stop_after_attempt(3),
    retry=retry_if_exception_type((RateLimitError, aiohttp.ClientError)),
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

    async with session.get(
        SEMANTIC_SCHOLAR_SEARCH_URL, headers=headers, params=params
    ) as resp:
        if resp.status == 429:
            retry_after = resp.headers.get("Retry-After", "3")
            wait_seconds = int(retry_after) if retry_after.isdigit() else 3
            logger.warning("Rate limited by Semantic Scholar, waiting %ds", wait_seconds)
            await asyncio.sleep(wait_seconds)
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
    params = {
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
        title = title_elem.text.strip().replace("\n", " ") if title_elem is not None and title_elem.text else ""
        
        abstract_elem = entry.find("atom:summary", ns)
        abstract = abstract_elem.text.strip().replace("\n", " ") if abstract_elem is not None and abstract_elem.text else ""
        
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
            papers.append(PaperMetadata(
                paper_id=f"arxiv:{paper_id}",
                title=title,
                authors=authors,
                abstract=abstract,
                url=url,
                year=year,
                doi=arxiv_doi,
                pdf_url=pdf_url,
                source=PaperSource.ARXIV,
            ))
    
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
    params = {
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
            papers.append(PaperMetadata(
                paper_id=f"pubmed:{pmid}",
                title=title,
                authors=authors,
                abstract="",
                url=url,
                year=year,
                doi=doi,
                source=PaperSource.PUBMED,
            ))
    
    return papers


async def search_semantic_scholar(
    queries: list[str],
    limit_per_query: int = 10,
) -> list[PaperMetadata]:
    timeout = aiohttp.ClientTimeout(total=60)
    async with aiohttp.ClientSession(timeout=timeout) as session:
        tasks = [_fetch_semantic_scholar(session, q, limit=limit_per_query, offset=0) for q in queries]
        results = await asyncio.gather(*tasks, return_exceptions=True)

    papers: list[PaperMetadata] = []
    seen_ids: set[str] = set()
    for r in results:
        if isinstance(r, BaseException):
            logger.error("Semantic Scholar search failed: %s", r)
            continue
        for raw in r.get("data", []):
            paper = _parse_semantic_scholar_paper(raw)
            if paper.paper_id and paper.paper_id not in seen_ids:
                seen_ids.add(paper.paper_id)
                papers.append(paper)
    return papers


async def search_arxiv(
    queries: list[str],
    limit_per_query: int = 10,
) -> list[PaperMetadata]:
    timeout = aiohttp.ClientTimeout(total=60)
    async with aiohttp.ClientSession(timeout=timeout) as session:
        tasks = [_fetch_arxiv(session, q, limit=limit_per_query) for q in queries]
        results = await asyncio.gather(*tasks, return_exceptions=True)

    papers: list[PaperMetadata] = []
    seen_ids: set[str] = set()
    for r in results:
        if isinstance(r, BaseException):
            logger.error("arXiv search failed: %s", r)
            continue
        for paper in _parse_arxiv_papers(r):
            if paper.paper_id and paper.paper_id not in seen_ids:
                seen_ids.add(paper.paper_id)
                papers.append(paper)
    return papers


async def search_pubmed(
    queries: list[str],
    limit_per_query: int = 10,
) -> list[PaperMetadata]:
    timeout = aiohttp.ClientTimeout(total=60)
    async with aiohttp.ClientSession(timeout=timeout) as session:
        id_tasks = [_fetch_pubmed_ids(session, q, limit=limit_per_query) for q in queries]
        id_results = await asyncio.gather(*id_tasks, return_exceptions=True)
        
        all_pmids: list[str] = []
        seen_pmids: set[str] = set()
        for r in id_results:
            if isinstance(r, BaseException):
                logger.error("PubMed ID search failed: %s", r)
                continue
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
    
    if PaperSource.SEMANTIC_SCHOLAR in sources:
        tasks.append(search_semantic_scholar(queries, limit_per_query))
        source_names.append("Semantic Scholar")
    
    if PaperSource.ARXIV in sources:
        tasks.append(search_arxiv(queries, limit_per_query))
        source_names.append("arXiv")
    
    if PaperSource.PUBMED in sources:
        tasks.append(search_pubmed(queries, limit_per_query))
        source_names.append("PubMed")
    
    if not tasks:
        return []
    
    results = await asyncio.gather(*tasks, return_exceptions=True)
    
    for i, r in enumerate(results):
        if isinstance(r, BaseException):
            logger.error("Search from %s failed: %s", source_names[i], r)
            continue
        all_papers.extend(r)
    
    return deduplicate_papers(all_papers)


async def search_papers(query: str, limit: int = 10) -> list[PaperMetadata]:
    return await search_semantic_scholar([query], limit_per_query=limit)


async def search_papers_batch(
    queries: list[str], limit_per_query: int = 10
) -> list[PaperMetadata]:
    return await search_semantic_scholar(queries, limit_per_query=limit_per_query)
