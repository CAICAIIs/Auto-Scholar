import asyncio
import json
import logging
import signal
import time
import uuid
from contextlib import asynccontextmanager
from ctypes import c_bool
from typing import Any

from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, Response, StreamingResponse
from prometheus_fastapi_instrumentator import Instrumentator
from pydantic import BaseModel

from backend.api.error_handlers import register_error_handlers
from backend.constants import WORKFLOW_TIMEOUT_SECONDS
from backend.evaluation.cost_tracker import get_total_cost_usd
from backend.evaluation.human_ratings import get_ratings_for_thread, save_rating
from backend.evaluation.runner import run_evaluation
from backend.evaluation.schemas import EvaluationResult, HumanRating
from backend.llm.health import get_model_health
from backend.schemas import (
    ApproveRequest,
    ApproveResponse,
    CitationStyle,
    ContinueRequest,
    ContinueResponse,
    ConversationMessage,
    DraftOutput,
    MessageRole,
    ModelConfig,
    PaperMetadata,
    PaperSource,
    SessionDetail,
    SessionSummary,
    StartRequest,
    StartResponse,
)
from backend.utils.charts import generate_all_charts
from backend.utils.citations import normalize_draft_citations
from backend.utils.clients import cleanup_clients
from backend.utils.event_queue import JsonFieldExtractor, StreamingEventQueue
from backend.utils.exporter import ExportFormat, export_to_docx, export_to_markdown
from backend.utils.http_pool import close_session
from backend.utils.llm_client import (
    cleanup_llm_clients,
    get_client,
    list_models,
    token_callback_var,
)
from backend.workflow import create_workflow

try:
    from backend.db.engine import dispose_engine
except Exception:  # pragma: no cover - db module may be unavailable in some environments
    dispose_engine = None

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)

SHUTDOWN_TASK_TIMEOUT_SECONDS = 30
SHUTDOWN_TOTAL_TIMEOUT_SECONDS = 45
SHUTDOWN_SSE_WAIT_SECONDS = 10
_shutdown_event = asyncio.Event()
is_shutting_down = c_bool(False)
_background_tasks: set[asyncio.Task[Any]] = set()
_active_sse_streams: set[str] = set()
DEPENDENCY_CHECK_TIMEOUT_SECONDS = 0.5


async def _check_dependency_health(
    dependency_name: str,
    check_fn: Any,
    timeout_seconds: float = DEPENDENCY_CHECK_TIMEOUT_SECONDS,
) -> tuple[bool, str | None]:
    try:
        await asyncio.wait_for(check_fn(), timeout=timeout_seconds)
        return True, None
    except Exception as exc:
        logger.warning("Dependency check failed for %s: %s", dependency_name, exc)
        return False, str(exc)


def _register_signal_handlers() -> None:
    def _handle_signal(signum: int, _frame: Any) -> None:
        if is_shutting_down.value:
            return
        is_shutting_down.value = True
        _shutdown_event.set()
        logger.info("Received signal %s, initiating graceful shutdown", signum)

    signal.signal(signal.SIGTERM, _handle_signal)
    signal.signal(signal.SIGINT, _handle_signal)


def _track_background_task(task: asyncio.Task[Any]) -> None:
    _background_tasks.add(task)
    task.add_done_callback(_background_tasks.discard)


async def _cancel_background_tasks() -> None:
    if not _background_tasks:
        logger.info("No background tasks to cancel")
        return

    logger.info("Cancelling %d background tasks", len(_background_tasks))
    for task in list(_background_tasks):
        task.cancel()

    done, pending = await asyncio.wait(_background_tasks, timeout=SHUTDOWN_TASK_TIMEOUT_SECONDS)
    logger.info("Background task cancellation result: done=%d pending=%d", len(done), len(pending))
    for task in pending:
        logger.warning("Background task did not finish before timeout: %s", task)


async def _run_cleanup_sequence() -> None:
    start_ts = time.perf_counter()
    logger.info("Graceful shutdown cleanup started at %.3f", start_ts)

    logger.info("Cleanup step: stop accepting new work")
    is_shutting_down.value = True
    _shutdown_event.set()

    logger.info("Cleanup step: wait for active SSE streams to finish")
    if _active_sse_streams:
        logger.info("Waiting for %d active SSE streams to finish", len(_active_sse_streams))
        for i in range(int(SHUTDOWN_SSE_WAIT_SECONDS * 2)):
            if not _active_sse_streams:
                logger.info("All SSE streams finished gracefully")
                break
            await asyncio.sleep(0.5)
        if _active_sse_streams:
            logger.warning(
                "Forcing shutdown with %d active streams: %s",
                len(_active_sse_streams),
                list(_active_sse_streams),
            )

    logger.info("Cleanup step: cancel background tasks")
    await _cancel_background_tasks()

    logger.info("Cleanup step: cleanup vector/db clients")
    await cleanup_clients()

    logger.info("Cleanup step: cleanup LLM clients")
    await cleanup_llm_clients()

    if dispose_engine is not None:
        logger.info("Cleanup step: dispose SQLAlchemy engine")
        await dispose_engine()
    else:
        logger.info("Cleanup step: dispose SQLAlchemy engine skipped (not available)")

    logger.info("Cleanup step: close shared HTTP session")
    await close_session()

    elapsed = time.perf_counter() - start_ts
    logger.info("Graceful shutdown cleanup completed in %.3fs", elapsed)
    if elapsed > SHUTDOWN_TOTAL_TIMEOUT_SECONDS:
        logger.warning(
            "Graceful shutdown exceeded target (%ss): %.3fs",
            SHUTDOWN_TOTAL_TIMEOUT_SECONDS,
            elapsed,
        )


@asynccontextmanager
async def lifespan(app: FastAPI):
    _register_signal_handlers()
    async with create_workflow(db_path="checkpoints.db") as graph:
        app.state.graph = graph
        logger.info("LangGraph workflow initialized")
        yield

    await asyncio.wait_for(_run_cleanup_sequence(), timeout=SHUTDOWN_TOTAL_TIMEOUT_SECONDS)
    logger.info("LangGraph workflow shut down")


app = FastAPI(title="Auto-Scholar API", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000", "http://127.0.0.1:3000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Register structured error handlers
register_error_handlers(app)

# Prometheus metrics instrumentation
# Exposes /metrics endpoint with http_requests_total, http_request_duration_seconds, etc.
Instrumentator().instrument(app).expose(app)

# Register health check routes
from backend.api.routes.health import router as health_router

app.include_router(health_router)


@app.get("/healthz")
async def healthz():
    """Liveness probe - returns 200 if process is alive."""
    return JSONResponse(content={"status": "ok"})


@app.get("/readyz")
async def readyz():
    """Readiness probe - checks if service can handle requests.

    Only checks core dependencies required for all requests.
    Optional features (vector pipeline) are not checked here.
    """
    checks: dict[str, bool] = {
        "workflow": hasattr(app.state, "graph") and app.state.graph is not None,
        "checkpoint_db": False,
        "shutdown": is_shutting_down.value,
    }
    errors: dict[str, str] = {}

    if not checks["workflow"]:
        errors["workflow"] = "workflow_not_initialized"

    if checks["shutdown"]:
        errors["shutdown"] = "service_shutting_down"

    if checks["workflow"]:
        try:
            checkpointer = app.state.graph.checkpointer
            async for _ in checkpointer.alist(None, limit=1):
                checks["checkpoint_db"] = True
                break
            if not checks["checkpoint_db"]:
                checks["checkpoint_db"] = True
        except Exception as e:
            logger.warning("Checkpoint DB health check failed: %s", e)
            errors["checkpoint_db"] = str(e)

    is_ready = checks["workflow"] and checks["checkpoint_db"] and not checks["shutdown"]
    payload: dict[str, Any] = {
        "status": "ready" if is_ready else "not ready",
        "checks": checks,
    }
    if errors:
        payload["errors"] = errors

    return JSONResponse(content=payload, status_code=200 if is_ready else 503)


@app.get("/startupz")
async def startupz():
    """Startup probe - validates workflow initialization and LLM connectivity.

    Runs once during pod startup. Checks critical dependencies that must be
    available before accepting traffic.
    """
    checks: dict[str, bool] = {
        "workflow": hasattr(app.state, "graph") and app.state.graph is not None,
        "llm_connectivity": False,
    }
    errors: dict[str, str] = {}

    if not checks["workflow"]:
        errors["workflow"] = "workflow_not_initialized"

    # Check LLM connectivity (lightweight models.list() call)
    # Only runs during startup, not on every readiness probe
    if checks["workflow"]:
        llm_check_result, llm_error = await _check_dependency_health(
            "llm_api", lambda: get_client().models.list(), timeout_seconds=2.0
        )
        checks["llm_connectivity"] = llm_check_result
        if not llm_check_result and llm_error:
            errors["llm_connectivity"] = llm_error

    is_started = checks["workflow"] and checks["llm_connectivity"]
    payload: dict[str, Any] = {
        "status": "started" if is_started else "not started",
        "workflow_initialized": checks["workflow"],
        "llm_connectivity": checks["llm_connectivity"],
    }
    if errors:
        payload["errors"] = errors

    return JSONResponse(content=payload, status_code=200 if is_started else 503)


def _get_config(thread_id: str) -> dict[str, Any]:
    return {"configurable": {"thread_id": thread_id}}


@app.post("/api/research/start", response_model=StartResponse)
async def start_research(req: StartRequest):
    thread_id = str(uuid.uuid4())
    config = _get_config(thread_id)
    graph = app.state.graph

    sources = (
        req.sources
        if req.sources
        else [
            PaperSource.SEMANTIC_SCHOLAR,
            PaperSource.ARXIV,
            PaperSource.PUBMED,
        ]
    )
    source_names = [s.value for s in sources]
    logger.info(
        "Starting research for thread %s: %s (sources: %s)", thread_id, req.query, source_names
    )

    initial_message = ConversationMessage(
        role=MessageRole.USER,
        content=req.query,
        metadata={"action": "start_research"},
    )

    try:
        result = await asyncio.wait_for(
            graph.ainvoke(
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
                    "current_agent": "",
                    "agent_handoffs": [],
                    "draft_outline": None,
                    "research_plan": None,
                    "reflection": None,
                    "model_id": req.model_id,
                },
                config=config,
            ),
            timeout=WORKFLOW_TIMEOUT_SECONDS,
        )
    except TimeoutError:
        logger.error(
            "Workflow timeout after %ds for thread %s", WORKFLOW_TIMEOUT_SECONDS, thread_id
        )
        raise HTTPException(
            status_code=504,
            detail=f"工作流超时 ({WORKFLOW_TIMEOUT_SECONDS}s)，请缩小搜索范围后重试",
        )
    except Exception as e:
        logger.exception("Workflow error for thread %s: %s", thread_id, e)
        raise HTTPException(
            status_code=500,
            detail=f"工作流执行错误: {type(e).__name__}: {str(e)[:200]}",
        )

    return StartResponse(
        thread_id=thread_id,
        candidate_papers=result.get("candidate_papers", []),
        logs=result.get("logs", []),
    )


@app.get("/api/research/stream/{thread_id}")
async def stream_research(thread_id: str):
    if is_shutting_down.value:
        raise HTTPException(status_code=503, detail="Service is shutting down")

    graph = app.state.graph
    config = _get_config(thread_id)

    snapshot = await graph.aget_state(config)
    if not snapshot.values:
        raise HTTPException(status_code=404, detail=f"Thread {thread_id} not found")

    _active_sse_streams.add(thread_id)
    logger.info(
        "SSE stream started for thread %s (active: %d)", thread_id, len(_active_sse_streams)
    )

    event_queue = StreamingEventQueue()

    async def producer():
        title_extractor = JsonFieldExtractor("title", buffer_until_complete=True)
        heading_extractor = JsonFieldExtractor("heading", buffer_until_complete=True)
        content_extractor = JsonFieldExtractor("content")

        async def _on_draft_token(token: str) -> None:
            title = title_extractor.feed(token)
            if title:
                formatted = f"# {title}\n\n"
                title_event = json.dumps(
                    {"event": "draft_token", "token": formatted}, ensure_ascii=False
                )
                await event_queue.push(title_event + "\n")

            heading = heading_extractor.feed(token)
            if heading:
                formatted = f"\n## {heading}\n\n"
                heading_event = json.dumps(
                    {"event": "draft_token", "token": formatted}, ensure_ascii=False
                )
                await event_queue.push(heading_event + "\n")

            content = content_extractor.feed(token)
            if content:
                content_event = json.dumps(
                    {"event": "draft_token", "token": content}, ensure_ascii=False
                )
                await event_queue.push(content_event + "\n")

        reset_token = token_callback_var.set(_on_draft_token)
        try:
            async for chunk in graph.astream(None, config=config, stream_mode="updates"):
                if is_shutting_down.value:
                    logger.info("Aborting stream for %s due to shutdown", thread_id)
                    await event_queue.push(
                        json.dumps({"event": "error", "detail": "Service shutting down"}) + "\n"
                    )
                    break
                for node_name, updates in chunk.items():
                    logs = updates.get("logs", [])
                    for log_entry in logs:
                        event_str = json.dumps(
                            {"node": node_name, "log": log_entry}, ensure_ascii=False
                        )
                        await event_queue.push(event_str + "\n")

                    # Emit research_plan when planner completes
                    research_plan = updates.get("research_plan")
                    if research_plan is not None:
                        plan_event = json.dumps(
                            {
                                "event": "research_plan",
                                "research_plan": research_plan.model_dump(mode="json"),
                            },
                            ensure_ascii=False,
                        )
                        await event_queue.push(plan_event + "\n")

                    # Emit reflection when reflection_agent completes
                    reflection = updates.get("reflection")
                    if reflection is not None:
                        reflection_event = json.dumps(
                            {
                                "event": "reflection",
                                "reflection": reflection.model_dump(mode="json"),
                            },
                            ensure_ascii=False,
                        )
                        await event_queue.push(reflection_event + "\n")

                    cost_event = json.dumps(
                        {
                            "event": "cost_update",
                            "node": node_name,
                            "total_cost_usd": get_total_cost_usd(),
                        },
                        ensure_ascii=False,
                    )
                    await event_queue.push(cost_event + "\n")

            final_state = await graph.aget_state(config)
            values = final_state.values or {}
            final_draft = values.get("final_draft")
            candidates = values.get("candidate_papers", [])

            if final_draft:
                selected = values.get("selected_papers")
                if not selected:
                    selected = [p for p in candidates if p.is_approved]
                normalize_draft_citations(final_draft, selected)

            # Include research_plan and reflection in completed payload
            research_plan_val = values.get("research_plan")
            reflection_val = values.get("reflection")

            completed_payload = {
                "event": "completed",
                "final_draft": (final_draft.model_dump(mode="json") if final_draft else None),
                "candidate_papers": [p.model_dump(mode="json") for p in candidates],
                "research_plan": (
                    research_plan_val.model_dump(mode="json") if research_plan_val else None
                ),
                "reflection": (reflection_val.model_dump(mode="json") if reflection_val else None),
            }
            await event_queue.push(json.dumps(completed_payload, ensure_ascii=False) + "\n")
        except Exception as e:
            logger.error("Stream error for thread %s: %s", thread_id, e)
            await event_queue.push(json.dumps({"event": "error", "detail": str(e)}) + "\n")
        finally:
            token_callback_var.reset(reset_token)
            await event_queue.close()

    async def event_generator():
        try:
            await event_queue.start()
            producer_task = asyncio.create_task(producer())
            _track_background_task(producer_task)
            async for chunk in event_queue.consume():
                if chunk == event_queue.HEARTBEAT_SENTINEL:
                    yield ": heartbeat\n\n"
                else:
                    yield f"data: {chunk}\n"
            stats = event_queue.get_stats()
            logger.info("Stream stats for %s: %s", thread_id, stats)
        finally:
            _active_sse_streams.discard(thread_id)
            logger.info(
                "SSE stream ended for thread %s (active: %d)", thread_id, len(_active_sse_streams)
            )

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "Connection": "keep-alive"},
    )


@app.post("/api/research/approve", status_code=202)
async def approve_papers(req: ApproveRequest):
    graph = app.state.graph
    config = _get_config(req.thread_id)

    snapshot = await graph.aget_state(config)
    if not snapshot.values:
        raise HTTPException(status_code=404, detail=f"Thread {req.thread_id} not found")

    if "extractor_agent" not in (snapshot.next or ()):
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

    logger.info(
        "Approved %d papers for thread %s, ready for streaming", approved_count, req.thread_id
    )

    return JSONResponse(
        status_code=202,
        content=ApproveResponse(
            thread_id=req.thread_id,
            approved_count=approved_count,
        ).model_dump(),
    )


@app.post("/api/research/continue", status_code=202)
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

    logger.info(
        "Continuing research for thread %s with message: %s", req.thread_id, req.message[:100]
    )

    await graph.aupdate_state(
        config,
        {
            "user_query": req.message,
            "messages": [user_message],
            "is_continuation": True,
            "qa_errors": [],
            "retry_count": 0,
            "model_id": req.model_id,
        },
        as_node="__start__",
    )

    return JSONResponse(
        status_code=202,
        content=ContinueResponse(
            thread_id=req.thread_id,
        ).model_dump(),
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
        "approved_count": len(
            [p for p in snapshot.values.get("candidate_papers", []) if p.is_approved]
        ),
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
        md_content = export_to_markdown(req.draft, req.papers, citation_style)
        return Response(
            content=md_content.encode("utf-8"),
            media_type="text/markdown; charset=utf-8",
            headers={
                "Content-Disposition": 'attachment; filename="review.md"',
            },
        )
    elif format == ExportFormat.DOCX:
        docx_content = export_to_docx(req.draft, req.papers, citation_style)
        return Response(
            content=docx_content,
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

        sessions.append(
            SessionSummary(
                thread_id=thread_id,
                user_query=user_query,
                status=status,
                paper_count=approved_count,
                has_draft=has_draft,
            )
        )

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


@app.get("/api/research/evaluate/{thread_id}", response_model=EvaluationResult)
async def evaluate_session(thread_id: str):
    graph = app.state.graph
    config = _get_config(thread_id)

    snapshot = await graph.aget_state(config)
    if not snapshot.values:
        raise HTTPException(status_code=404, detail=f"Session {thread_id} not found")

    values = snapshot.values
    draft = values.get("final_draft")
    if not draft:
        raise HTTPException(status_code=400, detail="Session has no completed draft to evaluate")

    candidates = values.get("candidate_papers", [])
    selected = values.get("selected_papers")
    if not selected:
        selected = [p for p in candidates if p.is_approved]
    logs = values.get("logs", [])
    language = values.get("output_language", "en")
    claim_verification = values.get("claim_verification")

    return run_evaluation(
        thread_id=thread_id,
        draft=draft,
        approved_papers=selected,
        logs=logs,
        language=language,
        claim_verification=claim_verification,
    )


@app.get("/api/models", response_model=list[ModelConfig])
async def get_available_models():
    return list_models()


class ModelHealthResponse(BaseModel):
    model_id: str
    provider: str
    state: str
    recent_failures: int
    last_failure_at: float | None = None


@app.get("/api/models/health", response_model=list[ModelHealthResponse])
async def get_model_health_status():
    return [
        ModelHealthResponse(
            model_id=health.model_id,
            provider=health.provider,
            state=health.state.value,
            recent_failures=health.recent_failures,
            last_failure_at=health.last_failure_at,
        )
        for health in (get_model_health(model) for model in list_models())
    ]


@app.post("/api/ratings", response_model=HumanRating)
async def submit_rating(rating: HumanRating):
    save_rating(rating)
    return rating


@app.get("/api/ratings/{thread_id}", response_model=list[HumanRating])
async def get_ratings(thread_id: str):
    return get_ratings_for_thread(thread_id)


@app.get("/api/debug/ingestion/{paper_id}")
async def debug_ingestion(paper_id: str):
    checks: dict[str, Any] = {}

    try:
        from backend.utils.rag_gateway_client import check_gateway_health

        checks["gateway_healthy"] = await check_gateway_health()
    except Exception as e:
        checks["gateway_healthy"] = None
        checks["gateway_error"] = str(e)

    try:
        from backend.utils.clients import get_minio_client

        minio = get_minio_client()
        if minio:
            from backend.constants import MINIO_BUCKET_RAW

            objects = list(
                minio.list_objects(MINIO_BUCKET_RAW, prefix=f"{paper_id}/", recursive=True)
            )
            checks["minio_pdf_exists"] = len(objects) > 0
            checks["minio_pdf_count"] = len(objects)
        else:
            checks["minio_pdf_exists"] = None
            checks["minio_note"] = "VECTOR_PIPELINE_ENABLED=false"
    except Exception as e:
        checks["minio_pdf_exists"] = None
        checks["minio_error"] = str(e)

    try:
        from backend.utils.clients import get_vector_store

        vs = await get_vector_store()
        if vs:
            count = await vs.count_by_paper_id(paper_id)
            checks["qdrant_chunk_count"] = count
        else:
            checks["qdrant_chunk_count"] = None
            checks["qdrant_note"] = "VECTOR_PIPELINE_ENABLED=false"
    except Exception as e:
        checks["qdrant_chunk_count"] = None
        checks["qdrant_error"] = str(e)

    try:
        from backend.utils.clients import get_redis_client

        redis = await get_redis_client()
        if redis:
            keys = await redis.keys(f"emb:*{paper_id}*")
            checks["redis_cache_keys"] = len(keys)
        else:
            checks["redis_cache_keys"] = None
            checks["redis_note"] = "VECTOR_PIPELINE_ENABLED=false"
    except Exception as e:
        checks["redis_cache_keys"] = None
        checks["redis_error"] = str(e)

    return {"paper_id": paper_id, "checks": checks}
