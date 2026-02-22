import pytest
import pytest_asyncio
import httpx
import uuid
from dotenv import load_dotenv

load_dotenv()

pytestmark = [pytest.mark.slow, pytest.mark.integration]


@pytest_asyncio.fixture
async def client():
    from app.main import app
    from app.workflow import create_workflow
    from contextlib import asynccontextmanager

    db_path = f"test_checkpoints_{uuid.uuid4().hex[:8]}.db"

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

    import os
    if os.path.exists(db_path):
        os.remove(db_path)


@pytest.mark.asyncio
async def test_full_workflow(client: httpx.AsyncClient):
    # Step 1: Start research — runs plan_node + search_node, then interrupts
    resp = await client.post(
        "/api/research/start",
        json={"query": "transformer architecture in natural language processing"},
        timeout=120.0,
    )
    assert resp.status_code == 200, f"Start failed: {resp.text}"
    data = resp.json()

    thread_id = data["thread_id"]
    candidate_papers = data["candidate_papers"]
    logs = data["logs"]

    assert thread_id, "thread_id should not be empty"
    assert len(candidate_papers) > 0, "Should have found candidate papers"
    assert len(logs) >= 2, f"Should have at least 2 log entries (plan + search), got: {logs}"

    print(f"\n=== START ===")
    print(f"Thread: {thread_id}")
    print(f"Candidates: {len(candidate_papers)}")
    print(f"Logs: {logs}")

    # Step 2: Check status — should be waiting at read_and_extract_node
    resp = await client.get(f"/api/research/status/{thread_id}")
    assert resp.status_code == 200
    status = resp.json()
    assert "read_and_extract_node" in status["next_nodes"], (
        f"Should be waiting at read_and_extract_node, got: {status['next_nodes']}"
    )

    print(f"\n=== STATUS ===")
    print(f"Next: {status['next_nodes']}")

    # Step 3: Approve first 3 papers (or all if fewer)
    papers_to_approve = candidate_papers[:3]
    paper_ids = [p["paper_id"] for p in papers_to_approve]

    print(f"\n=== APPROVING ===")
    print(f"Approving {len(paper_ids)} papers: {paper_ids}")

    resp = await client.post(
        "/api/research/approve",
        json={"thread_id": thread_id, "paper_ids": paper_ids},
        timeout=180.0,
    )
    assert resp.status_code == 200, f"Approve failed: {resp.text}"
    result = resp.json()

    assert result["approved_count"] == len(paper_ids)
    assert result["final_draft"] is not None, "Should have produced a final draft"

    draft = result["final_draft"]
    assert draft["title"], "Draft should have a title"
    assert len(draft["sections"]) > 0, "Draft should have sections"

    print(f"\n=== DRAFT ===")
    print(f"Title: {draft['title']}")
    print(f"Sections: {len(draft['sections'])}")
    for section in draft["sections"]:
        print(f"  - {section['heading']} (cites: {section['cited_paper_ids']})")

    all_logs = result["logs"]
    print("\n=== ALL LOGS ===")
    for log in all_logs:
        print(f"  {log}")

    assert len(all_logs) >= 3, f"Should have at least 3 log entries (extract, draft, QA), got {len(all_logs)}"


@pytest.mark.asyncio
async def test_status_not_found(client: httpx.AsyncClient):
    resp = await client.get("/api/research/status/nonexistent-thread-id")
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_approve_not_found(client: httpx.AsyncClient):
    resp = await client.post(
        "/api/research/approve",
        json={"thread_id": "nonexistent-thread-id", "paper_ids": ["fake"]},
    )
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_stream_endpoint(client: httpx.AsyncClient):
    resp = await client.post(
        "/api/research/start",
        json={"query": "deep learning optimization"},
        timeout=120.0,
    )
    assert resp.status_code == 200
    data = resp.json()
    thread_id = data["thread_id"]
    candidate_papers = data["candidate_papers"]

    paper_ids = [p["paper_id"] for p in candidate_papers[:2]]

    await client.post(
        "/api/research/approve",
        json={"thread_id": thread_id, "paper_ids": paper_ids},
        timeout=180.0,
    )

    resp = await client.post(
        "/api/research/start",
        json={"query": "reinforcement learning"},
        timeout=120.0,
    )
    assert resp.status_code == 200
    stream_thread_id = resp.json()["thread_id"]

    async with client.stream(
        "GET",
        f"/api/research/stream/{stream_thread_id}",
        timeout=180.0,
    ) as response:
        assert response.status_code == 200
        assert response.headers.get("content-type") == "text/event-stream; charset=utf-8"

        events: list[str] = []
        async for line in response.aiter_lines():
            if line.startswith("data:"):
                events.append(line)
                if '"event": "done"' in line or '"event":"done"' in line:
                    break

        assert len(events) > 0, "Should have received SSE events"
        print(f"\n=== STREAM TEST ===")
        print(f"Received {len(events)} SSE events")
        for e in events[:5]:
            print(f"  {e[:100]}...")
