import pytest
import pytest_asyncio
import httpx
import uuid
import os
from dotenv import load_dotenv

load_dotenv()

pytestmark = [pytest.mark.slow, pytest.mark.integration]


@pytest_asyncio.fixture
async def client():
    from app.main import app
    from app.workflow import create_workflow
    from contextlib import asynccontextmanager

    db_path = f"test_phase2_{uuid.uuid4().hex[:8]}.db"

    @asynccontextmanager
    async def test_lifespan(app):
        async with create_workflow(db_path=db_path) as graph:
            app.state.graph = graph
            yield

    async with test_lifespan(app):
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app),
            base_url="http://test",
        ) as c:
            yield c

    if os.path.exists(db_path):
        os.remove(db_path)


@pytest_asyncio.fixture
async def mocked_client():
    from app.main import app
    from app.workflow import create_workflow
    from contextlib import asynccontextmanager
    from unittest.mock import patch, AsyncMock

    db_path = f"test_phase2_mock_{uuid.uuid4().hex[:8]}.db"

    @asynccontextmanager
    async def test_lifespan(app):
        async with create_workflow(db_path=db_path) as graph:
            app.state.graph = graph
            yield

    from tests.conftest import MOCK_SEMANTIC_PAPERS, MOCK_ARXIV_PAPERS, MOCK_PUBMED_PAPERS

    async with test_lifespan(app):
        with patch(
            "app.utils.scholar_api.search_papers_multi_source",
            new=AsyncMock(return_value=MOCK_SEMANTIC_PAPERS + MOCK_ARXIV_PAPERS + MOCK_PUBMED_PAPERS),
        ):
            async with httpx.AsyncClient(
                transport=httpx.ASGITransport(app=app),
                base_url="http://test",
            ) as c:
                yield c

    if os.path.exists(db_path):
        os.remove(db_path)


class TestMultiSourceAPI:

    @pytest.mark.asyncio
    async def test_start_with_semantic_scholar_only(self, mocked_client: httpx.AsyncClient):
        resp = await mocked_client.post(
            "/api/research/start",
            json={
                "query": "transformer architecture",
                "language": "en",
                "sources": ["semantic_scholar"],
            },
            timeout=120.0,
        )
        assert resp.status_code == 200
        data = resp.json()
        assert "thread_id" in data
        assert "candidate_papers" in data
        assert len(data["logs"]) >= 1

    @pytest.mark.asyncio
    async def test_start_with_arxiv_only(self, mocked_client: httpx.AsyncClient):
        resp = await mocked_client.post(
            "/api/research/start",
            json={
                "query": "deep learning",
                "language": "en",
                "sources": ["arxiv"],
            },
            timeout=120.0,
        )
        assert resp.status_code == 200
        data = resp.json()
        assert "thread_id" in data
        assert "candidate_papers" in data

        for paper in data["candidate_papers"]:
            assert paper["source"] == "arxiv"
            assert paper["paper_id"].startswith("arxiv:")

    @pytest.mark.asyncio
    async def test_start_with_pubmed_only(self, mocked_client: httpx.AsyncClient):
        resp = await mocked_client.post(
            "/api/research/start",
            json={
                "query": "cancer treatment",
                "language": "en",
                "sources": ["pubmed"],
            },
            timeout=120.0,
        )
        assert resp.status_code == 200
        data = resp.json()
        assert "thread_id" in data
        assert "candidate_papers" in data

        for paper in data["candidate_papers"]:
            assert paper["source"] == "pubmed"
            assert paper["paper_id"].startswith("pubmed:")

    @pytest.mark.asyncio
    async def test_start_with_multiple_sources(self, mocked_client: httpx.AsyncClient):
        resp = await mocked_client.post(
            "/api/research/start",
            json={
                "query": "machine learning",
                "language": "en",
                "sources": ["semantic_scholar", "arxiv"],
            },
            timeout=120.0,
        )
        assert resp.status_code == 200
        data = resp.json()
        assert "thread_id" in data
        assert "candidate_papers" in data

        sources_found = {p["source"] for p in data["candidate_papers"]}
        assert len(sources_found) >= 1

    @pytest.mark.asyncio
    async def test_start_with_all_sources(self, mocked_client: httpx.AsyncClient):
        resp = await mocked_client.post(
            "/api/research/start",
            json={
                "query": "neural network",
                "language": "en",
                "sources": ["semantic_scholar", "arxiv", "pubmed"],
            },
            timeout=120.0,
        )
        assert resp.status_code == 200
        data = resp.json()
        assert "thread_id" in data
        assert len(data["candidate_papers"]) > 0

    @pytest.mark.asyncio
    async def test_start_default_source(self, mocked_client: httpx.AsyncClient):
        resp = await mocked_client.post(
            "/api/research/start",
            json={
                "query": "reinforcement learning",
                "language": "en",
            },
            timeout=120.0,
        )
        assert resp.status_code == 200
        data = resp.json()
        assert "candidate_papers" in data

        for paper in data["candidate_papers"]:
            assert paper["source"] == "semantic_scholar"

    @pytest.mark.asyncio
    async def test_logs_show_sources(self, mocked_client: httpx.AsyncClient):
        resp = await mocked_client.post(
            "/api/research/start",
            json={
                "query": "computer vision",
                "language": "en",
                "sources": ["semantic_scholar", "arxiv"],
            },
            timeout=120.0,
        )
        assert resp.status_code == 200
        data = resp.json()

        logs_text = " ".join(data["logs"])
        assert "semantic_scholar" in logs_text.lower() or "arxiv" in logs_text.lower()


class TestMultiSourceWorkflow:

    @pytest.mark.asyncio
    async def test_full_workflow_with_arxiv(self, mocked_client: httpx.AsyncClient):
        start_resp = await mocked_client.post(
            "/api/research/start",
            json={
                "query": "attention mechanism",
                "language": "en",
                "sources": ["arxiv"],
            },
            timeout=120.0,
        )
        assert start_resp.status_code == 200
        data = start_resp.json()
        thread_id = data["thread_id"]
        candidate_papers = data["candidate_papers"]

        if len(candidate_papers) == 0:
            pytest.skip("No papers found from arXiv")

        paper_ids = [p["paper_id"] for p in candidate_papers[:2]]
        approve_resp = await mocked_client.post(
            "/api/research/approve",
            json={"thread_id": thread_id, "paper_ids": paper_ids},
            timeout=180.0,
        )
        assert approve_resp.status_code == 200
        result = approve_resp.json()
        assert result["final_draft"] is not None

    @pytest.mark.asyncio
    async def test_full_workflow_with_mixed_sources(self, mocked_client: httpx.AsyncClient):
        start_resp = await mocked_client.post(
            "/api/research/start",
            json={
                "query": "image classification",
                "language": "en",
                "sources": ["semantic_scholar", "arxiv"],
            },
            timeout=120.0,
        )
        assert start_resp.status_code == 200
        data = start_resp.json()
        thread_id = data["thread_id"]
        candidate_papers = data["candidate_papers"]

        if len(candidate_papers) == 0:
            pytest.skip("No papers found")

        paper_ids = [p["paper_id"] for p in candidate_papers[:3]]
        approve_resp = await mocked_client.post(
            "/api/research/approve",
            json={"thread_id": thread_id, "paper_ids": paper_ids},
            timeout=180.0,
        )
        assert approve_resp.status_code == 200
        result = approve_resp.json()
        assert result["final_draft"] is not None
        assert result["approved_count"] == len(paper_ids)


class TestPaperSourceField:

    @pytest.mark.asyncio
    async def test_paper_has_source_field(self, mocked_client: httpx.AsyncClient):
        resp = await mocked_client.post(
            "/api/research/start",
            json={
                "query": "natural language processing",
                "language": "en",
                "sources": ["semantic_scholar"],
            },
            timeout=120.0,
        )
        assert resp.status_code == 200
        data = resp.json()

        for paper in data["candidate_papers"]:
            assert "source" in paper
            assert paper["source"] in ["semantic_scholar", "arxiv", "pubmed"]

    @pytest.mark.asyncio
    async def test_session_preserves_source(self, mocked_client: httpx.AsyncClient):
        start_resp = await mocked_client.post(
            "/api/research/start",
            json={
                "query": "graph neural network",
                "language": "en",
                "sources": ["arxiv"],
            },
            timeout=120.0,
        )
        assert start_resp.status_code == 200
        thread_id = start_resp.json()["thread_id"]

        session_resp = await mocked_client.get(f"/api/research/sessions/{thread_id}")
        assert session_resp.status_code == 200
        session = session_resp.json()

        for paper in session["candidate_papers"]:
            assert paper["source"] == "arxiv"
