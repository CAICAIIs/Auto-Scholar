import re
import time
from typing import Any

from backend.evaluation.schemas import CostEfficiencyResult

_usage_records: list[dict[str, Any]] = []
_timing_records: list[dict[str, Any]] = []


def record_llm_usage(
    prompt_tokens: int,
    completion_tokens: int,
    model: str = "",
    node: str = "",
) -> None:
    _usage_records.append(
        {
            "prompt_tokens": prompt_tokens,
            "completion_tokens": completion_tokens,
            "model": model,
            "node": node,
            "timestamp": time.time(),
        }
    )


def record_node_timing(node: str, duration_ms: float) -> None:
    _timing_records.append(
        {
            "node": node,
            "duration_ms": duration_ms,
            "timestamp": time.time(),
        }
    )


def reset_tracking() -> None:
    _usage_records.clear()
    _timing_records.clear()


def get_cost_efficiency_from_tracking() -> CostEfficiencyResult:
    total_prompt = sum(r["prompt_tokens"] for r in _usage_records)
    total_completion = sum(r["completion_tokens"] for r in _usage_records)
    total_llm_calls = len(_usage_records)

    node_timings: dict[str, float] = {}
    for r in _timing_records:
        node = r["node"]
        node_timings[node] = node_timings.get(node, 0) + r["duration_ms"]

    total_latency = sum(node_timings.values())

    return CostEfficiencyResult(
        prompt_tokens=total_prompt,
        completion_tokens=total_completion,
        total_llm_calls=total_llm_calls,
        total_search_calls=0,
        total_latency_ms=total_latency,
        node_timings=node_timings,
    )


NODE_TIMING_PATTERN = re.compile(r"\[(\w+)\] completed in ([\d.]+)s")


def parse_cost_from_logs(logs: list[str]) -> CostEfficiencyResult:
    node_timings: dict[str, float] = {}

    for log in logs:
        match = NODE_TIMING_PATTERN.search(log)
        if match:
            node = match.group(1)
            duration_s = float(match.group(2))
            duration_ms = duration_s * 1000
            node_timings[node] = node_timings.get(node, 0) + duration_ms

    total_latency = sum(node_timings.values())

    return CostEfficiencyResult(
        prompt_tokens=0,
        completion_tokens=0,
        total_llm_calls=0,
        total_search_calls=0,
        total_latency_ms=total_latency,
        node_timings=node_timings,
    )
