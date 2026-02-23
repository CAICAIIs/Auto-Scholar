import logging
import time
from collections.abc import AsyncIterator, Callable
from contextlib import asynccontextmanager
from functools import wraps
from typing import Any, Literal

from langgraph.checkpoint.sqlite.aio import AsyncSqliteSaver
from langgraph.graph import START, StateGraph
from langgraph.graph.state import CompiledStateGraph

from backend.evaluation.cost_tracker import record_node_timing
from backend.nodes import (
    critic_agent,
    extractor_agent,
    planner_agent,
    reflection_agent,
    retriever_agent,
    writer_agent,
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
        record_node_timing(func.__name__, elapsed_ms)
        return result

    return wrapper


_timed_planner_agent = _timed_node(planner_agent)
_timed_retriever_agent = _timed_node(retriever_agent)
_timed_extractor_agent = _timed_node(extractor_agent)
_timed_writer_agent = _timed_node(writer_agent)
_timed_critic_agent = _timed_node(critic_agent)
_timed_reflection_agent = _timed_node(reflection_agent)


def _entry_router(state: AgentState) -> Literal["planner_agent", "writer_agent"]:
    is_continuation = state.get("is_continuation", False)
    if is_continuation:
        return "writer_agent"
    return "planner_agent"


def _qa_router(state: AgentState) -> Literal["reflection_agent", "__end__"]:
    qa_errors = state.get("qa_errors", [])
    if not qa_errors:
        return "__end__"
    return "reflection_agent"


def _reflection_router(
    state: AgentState,
) -> Literal["writer_agent", "retriever_agent", "__end__"]:
    reflection = state.get("reflection")
    retry_count = state.get("retry_count", 0)

    if reflection is None or not reflection.should_retry:
        return "__end__"
    if retry_count >= MAX_RETRY_COUNT:
        return "__end__"

    if reflection.retry_target == "retriever_agent":
        return "retriever_agent"
    return "writer_agent"


def _build_graph() -> StateGraph:
    g = StateGraph(AgentState)
    g.add_node("planner_agent", _timed_planner_agent)  # type: ignore[call-overload]
    g.add_node("retriever_agent", _timed_retriever_agent)  # type: ignore[call-overload]
    g.add_node("extractor_agent", _timed_extractor_agent)  # type: ignore[call-overload]
    g.add_node("writer_agent", _timed_writer_agent)  # type: ignore[call-overload]
    g.add_node("critic_agent", _timed_critic_agent)  # type: ignore[call-overload]
    g.add_node("reflection_agent", _timed_reflection_agent)  # type: ignore[call-overload]

    g.add_conditional_edges(START, _entry_router)
    g.add_edge("planner_agent", "retriever_agent")
    g.add_edge("retriever_agent", "extractor_agent")
    g.add_edge("extractor_agent", "writer_agent")
    g.add_edge("writer_agent", "critic_agent")
    g.add_conditional_edges("critic_agent", _qa_router)
    g.add_conditional_edges("reflection_agent", _reflection_router)
    return g


@asynccontextmanager
async def create_workflow(
    db_path: str = "checkpoints.db",
) -> AsyncIterator[CompiledStateGraph]:
    async with AsyncSqliteSaver.from_conn_string(db_path) as saver:
        graph = _build_graph()
        compiled = graph.compile(
            checkpointer=saver,
            interrupt_before=["extractor_agent"],
        )
        yield compiled
