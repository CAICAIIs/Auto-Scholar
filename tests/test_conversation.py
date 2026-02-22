import os
import uuid
from unittest.mock import AsyncMock, patch

import httpx
import pytest
import pytest_asyncio
from dotenv import load_dotenv

load_dotenv()

pytestmark = [pytest.mark.slow, pytest.mark.integration]


@pytest_asyncio.fixture
async def mocked_client():
    from contextlib import asynccontextmanager

    from backend.main import app
    from backend.workflow import create_workflow

    db_path = f"test_conversation_{uuid.uuid4().hex[:8]}.db"

    @asynccontextmanager
    async def test_lifespan(app):
        async with create_workflow(db_path=db_path) as graph:
            app.state.graph = graph
            yield

    from tests.conftest import MOCK_SEMANTIC_PAPERS

    async with test_lifespan(app):
        with patch(
            "backend.utils.scholar_api.search_papers_multi_source",
            new=AsyncMock(return_value=MOCK_SEMANTIC_PAPERS),
        ):
            async with httpx.AsyncClient(
                transport=httpx.ASGITransport(app=app),
                base_url="http://test",
            ) as c:
                yield c

    if os.path.exists(db_path):
        os.remove(db_path)
    for suffix in ["-shm", "-wal"]:
        wal_path = db_path + suffix
        if os.path.exists(wal_path):
            os.remove(wal_path)


class TestConversationMessages:
    @pytest.mark.asyncio
    async def test_start_creates_initial_message(self, mocked_client: httpx.AsyncClient):
        resp = await mocked_client.post(
            "/api/research/start",
            json={"query": "transformer architecture", "language": "en"},
            timeout=120.0,
        )
        assert resp.status_code == 200
        data = resp.json()
        thread_id = data["thread_id"]

        session_resp = await mocked_client.get(f"/api/research/sessions/{thread_id}")
        assert session_resp.status_code == 200
        session = session_resp.json()

        assert "messages" in session
        assert len(session["messages"]) >= 1
        assert session["messages"][0]["role"] == "user"
        assert "transformer architecture" in session["messages"][0]["content"]

    @pytest.mark.asyncio
    async def test_session_detail_includes_messages(self, mocked_client: httpx.AsyncClient):
        resp = await mocked_client.post(
            "/api/research/start",
            json={"query": "deep learning optimization", "language": "en"},
            timeout=120.0,
        )
        assert resp.status_code == 200
        thread_id = resp.json()["thread_id"]

        session_resp = await mocked_client.get(f"/api/research/sessions/{thread_id}")
        assert session_resp.status_code == 200
        session = session_resp.json()

        assert "messages" in session
        assert isinstance(session["messages"], list)
        for msg in session["messages"]:
            assert "role" in msg
            assert "content" in msg
            assert msg["role"] in ["user", "assistant", "system"]


class TestContinueEndpoint:
    @pytest.mark.asyncio
    async def test_continue_requires_existing_thread(self, mocked_client: httpx.AsyncClient):
        resp = await mocked_client.post(
            "/api/research/continue",
            json={"thread_id": "nonexistent-thread", "message": "add more papers"},
            timeout=30.0,
        )
        assert resp.status_code == 404

    @pytest.mark.asyncio
    async def test_continue_requires_completed_draft(self, mocked_client: httpx.AsyncClient):
        start_resp = await mocked_client.post(
            "/api/research/start",
            json={"query": "neural networks", "language": "en"},
            timeout=120.0,
        )
        assert start_resp.status_code == 200
        thread_id = start_resp.json()["thread_id"]

        continue_resp = await mocked_client.post(
            "/api/research/continue",
            json={"thread_id": thread_id, "message": "expand the introduction"},
            timeout=30.0,
        )
        assert continue_resp.status_code == 400
        assert "no draft exists" in continue_resp.json()["detail"].lower()


class TestMultiTurnWorkflow:
    @pytest.mark.asyncio
    async def test_full_multi_turn_conversation(self, mocked_client: httpx.AsyncClient):
        start_resp = await mocked_client.post(
            "/api/research/start",
            json={"query": "attention mechanisms in NLP", "language": "en"},
            timeout=120.0,
        )
        assert start_resp.status_code == 200
        data = start_resp.json()
        thread_id = data["thread_id"]
        candidate_papers = data["candidate_papers"]

        assert len(candidate_papers) > 0

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
                    assert payload["final_draft"] is not None
                    break

        session_resp = await mocked_client.get(f"/api/research/sessions/{thread_id}")
        assert session_resp.status_code == 200
        session = session_resp.json()
        initial_message_count = len(session["messages"])
        assert initial_message_count >= 1

        continue_resp = await mocked_client.post(
            "/api/research/continue",
            json={
                "thread_id": thread_id,
                "message": "Please expand the methodology comparison section",
            },
        )
        assert continue_resp.status_code == 202

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
                    assert payload["final_draft"] is not None
                    break

        final_session_resp = await mocked_client.get(f"/api/research/sessions/{thread_id}")
        assert final_session_resp.status_code == 200
        final_session = final_session_resp.json()

        assert len(final_session["messages"]) > initial_message_count


class TestConversationContext:
    @pytest.mark.asyncio
    async def test_messages_have_timestamps(self, mocked_client: httpx.AsyncClient):
        resp = await mocked_client.post(
            "/api/research/start",
            json={"query": "reinforcement learning", "language": "en"},
            timeout=120.0,
        )
        assert resp.status_code == 200
        thread_id = resp.json()["thread_id"]

        session_resp = await mocked_client.get(f"/api/research/sessions/{thread_id}")
        assert session_resp.status_code == 200
        session = session_resp.json()

        for msg in session["messages"]:
            assert "timestamp" in msg
            assert msg["timestamp"] is not None

    @pytest.mark.asyncio
    async def test_messages_have_metadata(self, mocked_client: httpx.AsyncClient):
        resp = await mocked_client.post(
            "/api/research/start",
            json={"query": "computer vision", "language": "en"},
            timeout=120.0,
        )
        assert resp.status_code == 200
        thread_id = resp.json()["thread_id"]

        session_resp = await mocked_client.get(f"/api/research/sessions/{thread_id}")
        assert session_resp.status_code == 200
        session = session_resp.json()

        user_messages = [m for m in session["messages"] if m["role"] == "user"]
        assert len(user_messages) >= 1
        assert user_messages[0].get("metadata", {}).get("action") == "start_research"
