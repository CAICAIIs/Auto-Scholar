import logging
import time
from collections.abc import AsyncIterator, Callable
from contextlib import asynccontextmanager
from functools import wraps
from typing import Any, Literal

from langgraph.checkpoint.sqlite.aio import AsyncSqliteSaver
from langgraph.graph import START, StateGraph
from langgraph.graph.state import CompiledStateGraph

from backend.nodes import (
    draft_node,
    plan_node,
    qa_evaluator_node,
    read_and_extract_node,
    search_node,
)
from backend.state import AgentState

logger = logging.getLogger(__name__)

MAX_RETRY_COUNT = 3


def _timed_node(
    func: Callable[[AgentState], Any],
) -> Callable[[AgentState], Any]:
    @wraps(func)
    async def wrapper(state: AgentState) -> Any:
        start = time.perf_counter()
        result = await func(state)
        elapsed_ms = (time.perf_counter() - start) * 1000
        logger.info("%s completed in %.0fms", func.__name__, elapsed_ms)
        return result

    return wrapper


_timed_plan_node = _timed_node(plan_node)
_timed_search_node = _timed_node(search_node)
_timed_read_and_extract_node = _timed_node(read_and_extract_node)
_timed_draft_node = _timed_node(draft_node)
_timed_qa_evaluator_node = _timed_node(qa_evaluator_node)


def _entry_router(state: AgentState) -> Literal["plan_node", "draft_node"]:
    is_continuation = state.get("is_continuation", False)
    if is_continuation:
        return "draft_node"
    return "plan_node"


def _qa_router(state: AgentState) -> Literal["draft_node", "__end__"]:
    qa_errors = state.get("qa_errors", [])
    retry_count = state.get("retry_count", 0)

    if not qa_errors:
        return "__end__"

    if retry_count < MAX_RETRY_COUNT:
        return "draft_node"

    return "__end__"


def _build_graph() -> StateGraph:
    g = StateGraph(AgentState)
    g.add_node("plan_node", _timed_plan_node)  # type: ignore[call-overload]
    g.add_node("search_node", _timed_search_node)  # type: ignore[call-overload]
    g.add_node("read_and_extract_node", _timed_read_and_extract_node)  # type: ignore[call-overload]
    g.add_node("draft_node", _timed_draft_node)  # type: ignore[call-overload]
    g.add_node("qa_evaluator_node", _timed_qa_evaluator_node)  # type: ignore[call-overload]

    g.add_conditional_edges(START, _entry_router)
    g.add_edge("plan_node", "search_node")
    g.add_edge("search_node", "read_and_extract_node")
    g.add_edge("read_and_extract_node", "draft_node")
    g.add_edge("draft_node", "qa_evaluator_node")
    g.add_conditional_edges("qa_evaluator_node", _qa_router)
    return g


@asynccontextmanager
async def create_workflow(
    db_path: str = "checkpoints.db",
) -> AsyncIterator[CompiledStateGraph]:
    async with AsyncSqliteSaver.from_conn_string(db_path) as saver:
        graph = _build_graph()
        compiled = graph.compile(
            checkpointer=saver,
            interrupt_before=["read_and_extract_node"],
        )
        yield compiled
