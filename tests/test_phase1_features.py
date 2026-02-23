import os
import uuid

import httpx
import pytest
import pytest_asyncio
from dotenv import load_dotenv

from backend.schemas import DraftOutput, PaperMetadata, ReviewSection

load_dotenv()

pytestmark = [pytest.mark.slow, pytest.mark.integration]


@pytest_asyncio.fixture
async def client():
    from contextlib import asynccontextmanager

    from backend.main import app
    from backend.workflow import create_workflow

    db_path = f"test_phase1_{uuid.uuid4().hex[:8]}.db"

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
    from contextlib import asynccontextmanager
    from unittest.mock import patch

    from backend.main import app
    from backend.workflow import create_workflow

    db_path = f"test_phase1_mock_{uuid.uuid4().hex[:8]}.db"

    @asynccontextmanager
    async def test_lifespan(app):
        async with create_workflow(db_path=db_path) as graph:
            app.state.graph = graph
            yield

    from unittest.mock import AsyncMock

    from tests.conftest import MOCK_ARXIV_PAPERS, MOCK_PUBMED_PAPERS, MOCK_SEMANTIC_PAPERS

    all_papers = MOCK_SEMANTIC_PAPERS + MOCK_ARXIV_PAPERS + MOCK_PUBMED_PAPERS

    async with test_lifespan(app):
        with patch(
            "backend.utils.scholar_api.search_papers_multi_source",
            new=AsyncMock(return_value=all_papers),
        ):
            async with httpx.AsyncClient(
                transport=httpx.ASGITransport(app=app),
                base_url="http://test",
            ) as c:
                yield c

    if os.path.exists(db_path):
        os.remove(db_path)


class TestExportAPI:
    @pytest.fixture
    def sample_draft(self) -> DraftOutput:
        return DraftOutput(
            title="Test Literature Review: Machine Learning",
            sections=[
                ReviewSection(
                    heading="Introduction",
                    content="Machine learning has revolutionized many fields [1]. Recent advances in deep learning [2] have enabled new applications.",
                    cited_paper_ids=["paper1", "paper2"],
                ),
                ReviewSection(
                    heading="Methods",
                    content="Various methods have been proposed [1] including neural networks [2] and ensemble methods [3].",
                    cited_paper_ids=["paper1", "paper2", "paper3"],
                ),
                ReviewSection(
                    heading="Conclusion",
                    content="This review summarized key contributions from [1], [2], and [3].",
                    cited_paper_ids=["paper1", "paper2", "paper3"],
                ),
            ],
        )

    @pytest.fixture
    def sample_papers(self) -> list[PaperMetadata]:
        return [
            PaperMetadata(
                paper_id="paper1",
                title="Deep Learning: A Comprehensive Survey",
                authors=["Author A", "Author B", "Author C", "Author D"],
                abstract="A comprehensive survey of deep learning methods.",
                url="https://example.com/paper1",
                year=2023,
            ),
            PaperMetadata(
                paper_id="paper2",
                title="Neural Networks for Natural Language Processing",
                authors=["Author X", "Author Y"],
                abstract="Neural network approaches for NLP tasks.",
                url="https://example.com/paper2",
                year=2024,
            ),
            PaperMetadata(
                paper_id="paper3",
                title="Ensemble Methods in Machine Learning",
                authors=["Author M"],
                abstract="Overview of ensemble learning techniques.",
                url="https://example.com/paper3",
                year=2022,
            ),
        ]

    @pytest.mark.asyncio
    async def test_export_markdown(
        self,
        client: httpx.AsyncClient,
        sample_draft: DraftOutput,
        sample_papers: list[PaperMetadata],
    ):
        resp = await client.post(
            "/api/research/export?format=markdown",
            json={
                "draft": sample_draft.model_dump(),
                "papers": [p.model_dump() for p in sample_papers],
            },
        )
        assert resp.status_code == 200
        assert resp.headers.get("content-type") == "text/markdown; charset=utf-8"
        assert 'filename="review.md"' in resp.headers.get("content-disposition", "")

        content = resp.text
        assert "# Test Literature Review: Machine Learning" in content
        assert "## Introduction" in content
        assert "## Methods" in content
        assert "## Conclusion" in content
        assert "## References" in content
        assert "Deep Learning: A Comprehensive Survey" in content
        assert "Author A, Author B, Author C, & Author D" in content
        assert "(2023)" in content

    @pytest.mark.asyncio
    async def test_export_docx(
        self,
        client: httpx.AsyncClient,
        sample_draft: DraftOutput,
        sample_papers: list[PaperMetadata],
    ):
        resp = await client.post(
            "/api/research/export?format=docx",
            json={
                "draft": sample_draft.model_dump(),
                "papers": [p.model_dump() for p in sample_papers],
            },
        )
        assert resp.status_code == 200
        assert (
            "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
            in resp.headers.get("content-type", "")
        )
        assert 'filename="review.docx"' in resp.headers.get("content-disposition", "")

        content = resp.content
        assert len(content) > 0
        assert content[:4] == b"PK\x03\x04"

    @pytest.mark.asyncio
    async def test_export_empty_papers(self, client: httpx.AsyncClient, sample_draft: DraftOutput):
        resp = await client.post(
            "/api/research/export?format=markdown",
            json={
                "draft": sample_draft.model_dump(),
                "papers": [],
            },
        )
        assert resp.status_code == 200
        content = resp.text
        assert "# Test Literature Review" in content
        assert "## References" not in content

    @pytest.mark.asyncio
    async def test_export_invalid_format(
        self,
        client: httpx.AsyncClient,
        sample_draft: DraftOutput,
        sample_papers: list[PaperMetadata],
    ):
        resp = await client.post(
            "/api/research/export?format=pdf",
            json={
                "draft": sample_draft.model_dump(),
                "papers": [p.model_dump() for p in sample_papers],
            },
        )
        assert resp.status_code == 422


class TestSessionsAPI:
    @pytest.mark.asyncio
    async def test_list_sessions_empty(self, client: httpx.AsyncClient):
        resp = await client.get("/api/research/sessions")
        assert resp.status_code == 200
        sessions = resp.json()
        assert isinstance(sessions, list)

    @pytest.mark.asyncio
    async def test_list_sessions_with_limit(self, client: httpx.AsyncClient):
        resp = await client.get("/api/research/sessions?limit=10")
        assert resp.status_code == 200
        sessions = resp.json()
        assert isinstance(sessions, list)
        assert len(sessions) <= 10

    @pytest.mark.asyncio
    async def test_get_session_not_found(self, client: httpx.AsyncClient):
        resp = await client.get("/api/research/sessions/nonexistent-thread-id")
        assert resp.status_code == 404

    @pytest.mark.asyncio
    async def test_session_created_after_start(self, mocked_client: httpx.AsyncClient):
        start_resp = await mocked_client.post(
            "/api/research/start",
            json={"query": "transformer architecture", "language": "en"},
            timeout=120.0,
        )
        assert start_resp.status_code == 200
        thread_id = start_resp.json()["thread_id"]

        session_resp = await mocked_client.get(f"/api/research/sessions/{thread_id}")
        assert session_resp.status_code == 200
        session = session_resp.json()
        assert session["thread_id"] == thread_id
        assert session["user_query"] == "transformer architecture"
        assert session["status"] in ["in_progress", "pending"]
        assert isinstance(session["candidate_papers"], list)
        assert isinstance(session["logs"], list)

    @pytest.mark.asyncio
    async def test_session_appears_in_list(self, mocked_client: httpx.AsyncClient):
        start_resp = await mocked_client.post(
            "/api/research/start",
            json={"query": "deep learning optimization", "language": "en"},
            timeout=120.0,
        )
        assert start_resp.status_code == 200
        thread_id = start_resp.json()["thread_id"]

        list_resp = await mocked_client.get("/api/research/sessions?limit=50")
        assert list_resp.status_code == 200
        sessions = list_resp.json()

        our_session = next((s for s in sessions if s["thread_id"] == thread_id), None)
        assert our_session is not None
        assert our_session["user_query"] == "deep learning optimization"

    @pytest.mark.asyncio
    async def test_session_status_transitions(self, mocked_client: httpx.AsyncClient):
        start_resp = await mocked_client.post(
            "/api/research/start",
            json={"query": "neural network pruning", "language": "en"},
            timeout=120.0,
        )
        assert start_resp.status_code == 200
        data = start_resp.json()
        thread_id = data["thread_id"]
        candidate_papers = data["candidate_papers"]

        status_resp = await mocked_client.get(f"/api/research/status/{thread_id}")
        assert status_resp.status_code == 200
        status = status_resp.json()
        assert "extractor_agent" in status["next_nodes"]

        session_resp = await mocked_client.get(f"/api/research/sessions/{thread_id}")
        assert session_resp.status_code == 200
        session = session_resp.json()
        assert session["status"] == "in_progress"

        if len(candidate_papers) > 0:
            paper_ids = [p["paper_id"] for p in candidate_papers[:2]]
            approve_resp = await mocked_client.post(
                "/api/research/approve",
                json={"thread_id": thread_id, "paper_ids": paper_ids},
            )
            assert approve_resp.status_code == 202

            import json as _json

            async with mocked_client.stream(
                "GET",
                f"/api/research/stream/{thread_id}",
                timeout=300.0,
            ) as stream_resp:
                async for line in stream_resp.aiter_lines():
                    if not line.startswith("data:"):
                        continue
                    payload = _json.loads(line[len("data:") :].strip())
                    if payload.get("event") == "completed":
                        break

            session_resp = await mocked_client.get(f"/api/research/sessions/{thread_id}")
            assert session_resp.status_code == 200
            session = session_resp.json()
            assert session["status"] == "completed"
            assert session["final_draft"] is not None


class TestErrorHandling:
    @pytest.mark.asyncio
    async def test_start_with_empty_query(self, client: httpx.AsyncClient):
        resp = await client.post(
            "/api/research/start",
            json={"query": "", "language": "en"},
            timeout=30.0,
        )
        assert resp.status_code in [200, 422]

    @pytest.mark.asyncio
    async def test_approve_invalid_thread(self, client: httpx.AsyncClient):
        resp = await client.post(
            "/api/research/approve",
            json={"thread_id": "invalid-thread-id", "paper_ids": ["paper1"]},
        )
        assert resp.status_code == 404

    @pytest.mark.asyncio
    async def test_approve_invalid_paper_ids(self, mocked_client: httpx.AsyncClient):
        start_resp = await mocked_client.post(
            "/api/research/start",
            json={"query": "machine learning", "language": "en"},
            timeout=120.0,
        )
        assert start_resp.status_code == 200
        thread_id = start_resp.json()["thread_id"]

        resp = await mocked_client.post(
            "/api/research/approve",
            json={"thread_id": thread_id, "paper_ids": ["nonexistent-paper-id"]},
        )
        assert resp.status_code == 400
        assert "None of the provided paper_ids match" in resp.text

    @pytest.mark.asyncio
    async def test_status_invalid_thread(self, client: httpx.AsyncClient):
        resp = await client.get("/api/research/status/invalid-thread-id")
        assert resp.status_code == 404

    @pytest.mark.asyncio
    async def test_approve_wrong_state(self, mocked_client: httpx.AsyncClient):
        start_resp = await mocked_client.post(
            "/api/research/start",
            json={"query": "reinforcement learning", "language": "en"},
            timeout=120.0,
        )
        assert start_resp.status_code == 200
        data = start_resp.json()
        thread_id = data["thread_id"]
        candidate_papers = data["candidate_papers"]

        if len(candidate_papers) > 0:
            paper_ids = [p["paper_id"] for p in candidate_papers[:2]]
            resp = await mocked_client.post(
                "/api/research/approve",
                json={"thread_id": thread_id, "paper_ids": paper_ids},
            )
            assert resp.status_code == 202

            async with mocked_client.stream(
                "GET",
                f"/api/research/stream/{thread_id}",
                timeout=300.0,
            ) as stream_resp:
                async for line in stream_resp.aiter_lines():
                    if line.startswith("data:"):
                        if '"event":"completed"' in line or '"event": "completed"' in line:
                            break

            resp = await mocked_client.post(
                "/api/research/approve",
                json={"thread_id": thread_id, "paper_ids": paper_ids},
            )
            assert resp.status_code == 400
            assert "not waiting for approval" in resp.text


class TestLanguageSupport:
    @pytest.mark.asyncio
    async def test_start_with_english(self, mocked_client: httpx.AsyncClient):
        resp = await mocked_client.post(
            "/api/research/start",
            json={"query": "deep learning", "language": "en"},
            timeout=120.0,
        )
        assert resp.status_code == 200
        data = resp.json()
        assert "thread_id" in data
        assert "candidate_papers" in data

    @pytest.mark.asyncio
    async def test_start_with_chinese(self, mocked_client: httpx.AsyncClient):
        resp = await mocked_client.post(
            "/api/research/start",
            json={"query": "深度学习", "language": "zh"},
            timeout=120.0,
        )
        assert resp.status_code == 200
        data = resp.json()
        assert "thread_id" in data
        assert "candidate_papers" in data

    @pytest.mark.asyncio
    async def test_default_language_is_english(self, mocked_client: httpx.AsyncClient):
        resp = await mocked_client.post(
            "/api/research/start",
            json={"query": "neural networks"},
            timeout=120.0,
        )
        assert resp.status_code == 200


class TestFullWorkflow:
    @pytest.mark.asyncio
    async def test_complete_workflow_with_export(self, mocked_client: httpx.AsyncClient):
        start_resp = await mocked_client.post(
            "/api/research/start",
            json={"query": "attention mechanism in transformers", "language": "en"},
            timeout=120.0,
        )
        assert start_resp.status_code == 200
        data = start_resp.json()
        thread_id = data["thread_id"]
        candidate_papers = data["candidate_papers"]

        assert len(candidate_papers) > 0, "Should find candidate papers"

        paper_ids = [p["paper_id"] for p in candidate_papers[:3]]
        approve_resp = await mocked_client.post(
            "/api/research/approve",
            json={"thread_id": thread_id, "paper_ids": paper_ids},
        )
        assert approve_resp.status_code == 202

        import json as _json

        completed_data = None
        async with mocked_client.stream(
            "GET",
            f"/api/research/stream/{thread_id}",
            timeout=300.0,
        ) as stream_resp:
            async for line in stream_resp.aiter_lines():
                if not line.startswith("data:"):
                    continue
                payload = _json.loads(line[len("data:") :].strip())
                if payload.get("event") == "completed":
                    completed_data = payload
                    break

        assert completed_data is not None
        draft = completed_data["final_draft"]
        assert draft is not None

        approved_papers = [p for p in candidate_papers if p["paper_id"] in paper_ids]

        export_resp = await mocked_client.post(
            "/api/research/export?format=markdown",
            json={
                "draft": draft,
                "papers": approved_papers,
            },
        )
        assert export_resp.status_code == 200
        markdown_content = export_resp.text
        assert draft["title"] in markdown_content

        export_resp = await mocked_client.post(
            "/api/research/export?format=docx",
            json={
                "draft": draft,
                "papers": approved_papers,
            },
        )
        assert export_resp.status_code == 200
        assert export_resp.content[:4] == b"PK\x03\x04"

        session_resp = await mocked_client.get(f"/api/research/sessions/{thread_id}")
        assert session_resp.status_code == 200
        session = session_resp.json()
        assert session["status"] == "completed"
        assert session["final_draft"] is not None
