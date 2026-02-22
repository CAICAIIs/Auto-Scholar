import asyncio
import json
import logging
import uuid
from contextlib import asynccontextmanager
from typing import Any

from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse, Response
from pydantic import BaseModel
import re

from app.schemas import PaperMetadata, DraftOutput, StartRequest, ReviewSection, SessionSummary, SessionDetail, PaperSource, CitationStyle, ContinueRequest, ContinueResponse, ConversationMessage, MessageRole
from app.utils.event_queue import StreamingEventQueue
from app.utils.exporter import ExportFormat, export_to_markdown, export_to_docx
from app.utils.charts import generate_all_charts
from app.utils.http_pool import close_session
from app.workflow import create_workflow

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)


class StartResponse(BaseModel):
    thread_id: str
    candidate_papers: list[PaperMetadata]
    logs: list[str]


class ApproveRequest(BaseModel):
    thread_id: str
    paper_ids: list[str]


class ApproveResponse(BaseModel):
    thread_id: str
    final_draft: DraftOutput | None
    approved_count: int
    logs: list[str]


@asynccontextmanager
async def lifespan(app: FastAPI):
    async with create_workflow(db_path="checkpoints.db") as graph:
        app.state.graph = graph
        logger.info("LangGraph workflow initialized")
        yield
    await close_session()
    logger.info("LangGraph workflow shut down")


app = FastAPI(title="Auto-Scholar API", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000", "http://127.0.0.1:3000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


def _get_config(thread_id: str) -> dict[str, Any]:
    return {"configurable": {"thread_id": thread_id}}


@app.post("/api/research/start", response_model=StartResponse)
async def start_research(req: StartRequest):
    thread_id = str(uuid.uuid4())
    config = _get_config(thread_id)
    graph = app.state.graph

    sources = req.sources if req.sources else [PaperSource.SEMANTIC_SCHOLAR]
    source_names = [s.value for s in sources]
    logger.info("Starting research for thread %s: %s (sources: %s)", thread_id, req.query, source_names)

    initial_message = ConversationMessage(
        role=MessageRole.USER,
        content=req.query,
        metadata={"action": "start_research"},
    )

    result = await graph.ainvoke(
        {
            "task_id": thread_id,
            "user_query": req.query,
            "output_language": req.language,
            "search_sources": sources,
            "search_keywords": [],
            "candidate_papers": [],
            "approved_papers": [],
            "final_draft": None,
            "qa_errors": [],
            "retry_count": 0,
            "logs": [],
            "messages": [initial_message],
            "is_continuation": False,
        },
        config=config,
    )

    return StartResponse(
        thread_id=thread_id,
        candidate_papers=result.get("candidate_papers", []),
        logs=result.get("logs", []),
    )


@app.get("/api/research/stream/{thread_id}")
async def stream_research(thread_id: str):
    graph = app.state.graph
    config = _get_config(thread_id)

    snapshot = await graph.aget_state(config)
    if not snapshot.values:
        raise HTTPException(status_code=404, detail=f"Thread {thread_id} not found")

    event_queue = StreamingEventQueue()

    async def producer():
        try:
            async for chunk in graph.astream(None, config=config, stream_mode="updates"):
                for node_name, updates in chunk.items():
                    logs = updates.get("logs", [])
                    for log_entry in logs:
                        event_str = json.dumps({"node": node_name, "log": log_entry}, ensure_ascii=False)
                        await event_queue.push(event_str + "\n")
            await event_queue.push(json.dumps({"event": "done"}) + "\n")
        except Exception as e:
            logger.error("Stream error for thread %s: %s", thread_id, e)
            await event_queue.push(json.dumps({"event": "error", "detail": str(e)}) + "\n")
        finally:
            await event_queue.close()

    async def event_generator():
        await event_queue.start()
        asyncio.create_task(producer())
        async for chunk in event_queue.consume():
            yield f"data: {chunk}\n"
        stats = event_queue.get_stats()
        logger.info("Stream stats for %s: %s", thread_id, stats)

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "Connection": "keep-alive"},
    )


@app.post("/api/research/approve", response_model=ApproveResponse)
async def approve_papers(req: ApproveRequest):
    graph = app.state.graph
    config = _get_config(req.thread_id)

    snapshot = await graph.aget_state(config)
    if not snapshot.values:
        raise HTTPException(status_code=404, detail=f"Thread {req.thread_id} not found")

    if "read_and_extract_node" not in (snapshot.next or ()):
        raise HTTPException(
            status_code=400,
            detail=f"Thread {req.thread_id} is not waiting for approval. Next: {snapshot.next}",
        )

    candidates: list[PaperMetadata] = snapshot.values.get("candidate_papers", [])
    approved_ids = set(req.paper_ids)

    updated_candidates: list[PaperMetadata] = []
    approved_count = 0
    for paper in candidates:
        if paper.paper_id in approved_ids:
            updated = paper.model_copy(update={"is_approved": True})
            updated_candidates.append(updated)
            approved_count += 1
        else:
            updated_candidates.append(paper)

    if approved_count == 0:
        raise HTTPException(
            status_code=400,
            detail="None of the provided paper_ids match candidate papers",
        )

    await graph.aupdate_state(
        config,
        {"candidate_papers": updated_candidates},
    )

    existing_log_count = len(snapshot.values.get("logs", []))
    logger.info("Approved %d papers for thread %s, resuming workflow", approved_count, req.thread_id)

    result = await graph.ainvoke(None, config=config)

    all_logs = result.get("logs", [])
    new_logs = all_logs[existing_log_count:]

    final_draft = result.get("final_draft")

    if final_draft:
        approved_list = [p for p in updated_candidates if p.is_approved]
        max_index = len(approved_list)
        index_to_id = {i + 1: p.paper_id for i, p in enumerate(approved_list)}

        for section in final_draft.sections:
            pattern = r'\{cite:(\d+)\}'

            def replace_match(m: re.Match[str]) -> str:
                idx = int(m.group(1))
                if 1 <= idx <= max_index:
                    return f"[{idx}]"
                logger.warning("Citation index %d out of range (1-%d), removing", idx, max_index)
                return ""

            section.content = re.sub(pattern, replace_match, section.content)
            cited_indices = [
                int(n) for n in re.findall(r'\[(\d+)\]', section.content)
                if 1 <= int(n) <= max_index
            ]
            section.cited_paper_ids = [
                index_to_id[idx] for idx in sorted(set(cited_indices))
            ]

    return ApproveResponse(
        thread_id=req.thread_id,
        final_draft=final_draft,
        approved_count=approved_count,
        logs=new_logs,
    )


@app.post("/api/research/continue", response_model=ContinueResponse)
async def continue_research(req: ContinueRequest):
    graph = app.state.graph
    config = _get_config(req.thread_id)

    snapshot = await graph.aget_state(config)
    if not snapshot.values:
        raise HTTPException(status_code=404, detail=f"Thread {req.thread_id} not found")

    if not snapshot.values.get("final_draft"):
        raise HTTPException(
            status_code=400,
            detail="Cannot continue: no draft exists yet. Complete the initial workflow first.",
        )

    user_message = ConversationMessage(
        role=MessageRole.USER,
        content=req.message,
        metadata={"action": "continue_research"},
    )

    existing_log_count = len(snapshot.values.get("logs", []))
    logger.info("Continuing research for thread %s with message: %s", req.thread_id, req.message[:100])

    await graph.aupdate_state(
        config,
        {
            "user_query": req.message,
            "messages": [user_message],
            "is_continuation": True,
            "qa_errors": [],
            "retry_count": 0,
        },
        as_node="__start__",
    )

    result = await graph.ainvoke(None, config=config)

    all_logs = result.get("logs", [])
    new_logs = all_logs[existing_log_count:]

    assistant_message = ConversationMessage(
        role=MessageRole.ASSISTANT,
        content=f"Updated draft based on: {req.message}",
        metadata={"action": "draft_updated", "has_draft": result.get("final_draft") is not None},
    )

    await graph.aupdate_state(
        config,
        {"messages": [assistant_message]},
    )

    final_draft = result.get("final_draft")
    if final_draft:
        candidates = result.get("candidate_papers", [])
        approved_list = [p for p in candidates if p.is_approved]
        max_index = len(approved_list)
        index_to_id = {i + 1: p.paper_id for i, p in enumerate(approved_list)}

        for section in final_draft.sections:
            pattern = r'\{cite:(\d+)\}'

            def replace_match(m: re.Match[str]) -> str:
                idx = int(m.group(1))
                if 1 <= idx <= max_index:
                    return f"[{idx}]"
                logger.warning("Citation index %d out of range (1-%d), removing", idx, max_index)
                return ""

            section.content = re.sub(pattern, replace_match, section.content)
            cited_indices = [
                int(n) for n in re.findall(r'\[(\d+)\]', section.content)
                if 1 <= int(n) <= max_index
            ]
            section.cited_paper_ids = [
                index_to_id[idx] for idx in sorted(set(cited_indices))
            ]

    return ContinueResponse(
        thread_id=req.thread_id,
        message=assistant_message,
        final_draft=final_draft,
        candidate_papers=result.get("candidate_papers", []),
        logs=new_logs,
    )


@app.get("/api/research/status/{thread_id}")
async def get_status(thread_id: str):
    graph = app.state.graph
    config = _get_config(thread_id)

    snapshot = await graph.aget_state(config)
    if not snapshot.values:
        raise HTTPException(status_code=404, detail=f"Thread {thread_id} not found")

    return {
        "thread_id": thread_id,
        "next_nodes": list(snapshot.next) if snapshot.next else [],
        "logs": snapshot.values.get("logs", []),
        "has_draft": snapshot.values.get("final_draft") is not None,
        "candidate_count": len(snapshot.values.get("candidate_papers", [])),
        "approved_count": len([
            p for p in snapshot.values.get("candidate_papers", []) if p.is_approved
        ]),
    }


class ExportRequest(BaseModel):
    draft: DraftOutput
    papers: list[PaperMetadata]


@app.post("/api/research/export")
async def export_review(
    req: ExportRequest,
    format: ExportFormat = Query(default=ExportFormat.MARKDOWN),
    citation_style: CitationStyle = Query(default=CitationStyle.APA),
):
    if format == ExportFormat.MARKDOWN:
        content = export_to_markdown(req.draft, req.papers, citation_style)
        return Response(
            content=content.encode("utf-8"),
            media_type="text/markdown; charset=utf-8",
            headers={
                "Content-Disposition": 'attachment; filename="review.md"',
            },
        )
    elif format == ExportFormat.DOCX:
        content = export_to_docx(req.draft, req.papers, citation_style)
        return Response(
            content=content,
            media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            headers={
                "Content-Disposition": 'attachment; filename="review.docx"',
            },
        )
    else:
        raise HTTPException(status_code=400, detail=f"Unsupported format: {format}")


class ChartsRequest(BaseModel):
    papers: list[PaperMetadata]


class ChartsResponse(BaseModel):
    year_trend: str | None
    source_distribution: str | None
    author_frequency: str | None


@app.post("/api/research/charts", response_model=ChartsResponse)
async def get_charts(req: ChartsRequest):
    charts = generate_all_charts(req.papers)
    return ChartsResponse(**charts)


@app.get("/api/research/sessions", response_model=list[SessionSummary])
async def list_sessions(limit: int = Query(default=50, le=100)):
    graph = app.state.graph
    checkpointer = graph.checkpointer

    sessions: list[SessionSummary] = []
    seen_threads: set[str] = set()

    async for checkpoint_tuple in checkpointer.alist(None, limit=limit * 2):
        thread_id = checkpoint_tuple.config["configurable"].get("thread_id")
        if not thread_id or thread_id in seen_threads:
            continue
        seen_threads.add(thread_id)

        values = checkpoint_tuple.checkpoint.get("channel_values", {}) or {}
        user_query = values.get("user_query", "")
        if not user_query:
            continue

        candidates = values.get("candidate_papers", [])
        approved_count = len([p for p in candidates if p.is_approved])
        has_draft = values.get("final_draft") is not None

        if has_draft:
            status = "completed"
        elif approved_count > 0:
            status = "in_progress"
        else:
            status = "pending"

        sessions.append(SessionSummary(
            thread_id=thread_id,
            user_query=user_query,
            status=status,
            paper_count=approved_count,
            has_draft=has_draft,
        ))

        if len(sessions) >= limit:
            break

    return sessions


@app.get("/api/research/sessions/{thread_id}", response_model=SessionDetail)
async def get_session(thread_id: str):
    graph = app.state.graph
    config = _get_config(thread_id)

    snapshot = await graph.aget_state(config)
    if not snapshot.values:
        raise HTTPException(status_code=404, detail=f"Session {thread_id} not found")

    values = snapshot.values
    candidates = values.get("candidate_papers", [])
    approved = [p for p in candidates if p.is_approved]

    if snapshot.next:
        status = "in_progress"
    elif values.get("final_draft"):
        status = "completed"
    else:
        status = "pending"

    return SessionDetail(
        thread_id=thread_id,
        user_query=values.get("user_query", ""),
        status=status,
        candidate_papers=candidates,
        approved_papers=approved,
        final_draft=values.get("final_draft"),
        logs=values.get("logs", []),
        messages=values.get("messages", []),
    )
