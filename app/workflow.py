from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Literal

from langgraph.checkpoint.sqlite.aio import AsyncSqliteSaver
from langgraph.graph import StateGraph, START
from langgraph.graph.state import CompiledStateGraph

from app.state import AgentState
from app.nodes import plan_node, search_node, read_and_extract_node, draft_node, qa_evaluator_node


MAX_RETRY_COUNT = 3


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
    g.add_node("plan_node", plan_node)
    g.add_node("search_node", search_node)
    g.add_node("read_and_extract_node", read_and_extract_node)
    g.add_node("draft_node", draft_node)
    g.add_node("qa_evaluator_node", qa_evaluator_node)

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
