import re
import time
from typing import Any

from backend.evaluation.schemas import CostEfficiencyResult, TaskCostBreakdown

_usage_records: list[dict[str, Any]] = []
_timing_records: list[dict[str, Any]] = []
_search_records: list[dict[str, str]] = []

# USD per 1M tokens (input, output). Updated 2025-02.
PRICING_TABLE: dict[str, tuple[float, float]] = {
    "gpt-4o": (2.50, 10.00),
    "gpt-4o-mini": (0.15, 0.60),
    "gpt-4-turbo": (10.00, 30.00),
    "gpt-4": (30.00, 60.00),
    "gpt-3.5-turbo": (0.50, 1.50),
    "o1": (15.00, 60.00),
    "o1-mini": (3.00, 12.00),
    "o3-mini": (1.10, 4.40),
    "deepseek-chat": (0.14, 0.28),
    "deepseek-reasoner": (0.55, 2.19),
}

_DEFAULT_PRICE: tuple[float, float] = (2.50, 10.00)


def estimate_cost_usd(prompt_tokens: int, completion_tokens: int, model: str) -> float:
    model_lower = model.lower()
    price = PRICING_TABLE.get(model_lower)
    if not price:
        best_key = ""
        for key, val in PRICING_TABLE.items():
            if key in model_lower and len(key) > len(best_key):
                best_key = key
                price = val
    if not price:
        price = _DEFAULT_PRICE
    input_cost = (prompt_tokens / 1_000_000) * price[0]
    output_cost = (completion_tokens / 1_000_000) * price[1]
    return round(input_cost + output_cost, 6)


def record_search_call(source: str) -> None:
    _search_records.append({"source": source, "timestamp": str(time.time())})


def record_llm_usage(
    prompt_tokens: int,
    completion_tokens: int,
    model: str = "",
    node: str = "",
    task_type: str = "",
) -> dict[str, Any]:
    cost_usd = estimate_cost_usd(prompt_tokens, completion_tokens, model)
    record = {
        "prompt_tokens": prompt_tokens,
        "completion_tokens": completion_tokens,
        "model": model,
        "node": node,
        "task_type": task_type,
        "cost_usd": cost_usd,
        "timestamp": time.time(),
    }
    _usage_records.append(record)
    return record


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
    _search_records.clear()


def get_total_cost_usd() -> float:
    return round(sum(r["cost_usd"] for r in _usage_records), 6)


def get_cost_efficiency_from_tracking() -> CostEfficiencyResult:
    total_prompt = sum(r["prompt_tokens"] for r in _usage_records)
    total_completion = sum(r["completion_tokens"] for r in _usage_records)
    total_llm_calls = len(_usage_records)
    total_search_calls = len(_search_records)

    node_timings: dict[str, float] = {}
    for r in _timing_records:
        node = r["node"]
        node_timings[node] = node_timings.get(node, 0) + r["duration_ms"]

    total_latency = sum(node_timings.values())

    task_agg: dict[str, dict[str, Any]] = {}
    for r in _usage_records:
        tt = r.get("task_type", "") or "unknown"
        if tt not in task_agg:
            task_agg[tt] = {
                "prompt_tokens": 0,
                "completion_tokens": 0,
                "llm_calls": 0,
                "cost_usd": 0.0,
            }
        task_agg[tt]["prompt_tokens"] += r["prompt_tokens"]
        task_agg[tt]["completion_tokens"] += r["completion_tokens"]
        task_agg[tt]["llm_calls"] += 1
        task_agg[tt]["cost_usd"] += r["cost_usd"]

    task_breakdown = [
        TaskCostBreakdown(
            task_type=tt,
            prompt_tokens=agg["prompt_tokens"],
            completion_tokens=agg["completion_tokens"],
            llm_calls=agg["llm_calls"],
            cost_usd=round(agg["cost_usd"], 6),
        )
        for tt, agg in sorted(task_agg.items())
    ]

    return CostEfficiencyResult(
        prompt_tokens=total_prompt,
        completion_tokens=total_completion,
        total_llm_calls=total_llm_calls,
        total_search_calls=total_search_calls,
        total_latency_ms=total_latency,
        node_timings=node_timings,
        total_cost_usd=get_total_cost_usd(),
        task_breakdown=task_breakdown,
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
