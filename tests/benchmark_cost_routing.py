#!/usr/bin/env python3
"""Cost comparison: single-model (gpt-4o) vs task-aware routing.

Usage: python tests/benchmark_cost_routing.py
"""

import os
import sys
from pathlib import Path

project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))
os.chdir(project_root)

from backend.evaluation.cost_tracker import PRICING_TABLE, estimate_cost_usd
from backend.llm.router import _score_model, select_model
from backend.llm.task_types import TASK_REQUIREMENTS, TaskType
from backend.schemas import CostTier, ModelConfig, ModelProvider

# (num_calls, avg_prompt_tokens, avg_completion_tokens)
TASK_PROFILES_10_PAPERS: dict[str, tuple[int, int, int]] = {
    "planning": (1, 800, 600),
    "extraction": (10, 2000, 800),
    "writing": (6, 4000, 1500),
    "qa": (1, 3000, 500),
    "reflection": (1, 2000, 600),
}

TASK_PROFILES_5_PAPERS: dict[str, tuple[int, int, int]] = {
    "planning": (1, 800, 600),
    "extraction": (5, 2000, 800),
    "writing": (4, 3000, 1200),
    "qa": (1, 2000, 400),
    "reflection": (1, 1500, 500),
}

MODELS: dict[str, ModelConfig] = {
    "openai:gpt-4o": ModelConfig(
        id="openai:gpt-4o",
        provider=ModelProvider.OPENAI,
        model_name="gpt-4o",
        display_name="GPT-4o",
        api_base="https://api.openai.com/v1",
        api_key_env="LLM_API_KEY",
        supports_json_mode=True,
        supports_structured_output=True,
        max_output_tokens=8192,
        is_local=False,
        max_context_tokens=128000,
        supports_long_context=True,
        cost_tier=CostTier.HIGH,
        reasoning_score=8,
        creativity_score=8,
        latency_score=6,
    ),
    "openai:gpt-4o-mini": ModelConfig(
        id="openai:gpt-4o-mini",
        provider=ModelProvider.OPENAI,
        model_name="gpt-4o-mini",
        display_name="GPT-4o Mini",
        api_base="https://api.openai.com/v1",
        api_key_env="LLM_API_KEY",
        supports_json_mode=True,
        supports_structured_output=True,
        max_output_tokens=8192,
        is_local=False,
        max_context_tokens=128000,
        supports_long_context=True,
        cost_tier=CostTier.LOW,
        reasoning_score=6,
        creativity_score=5,
        latency_score=9,
    ),
    "deepseek:deepseek-chat": ModelConfig(
        id="deepseek:deepseek-chat",
        provider=ModelProvider.DEEPSEEK,
        model_name="deepseek-chat",
        display_name="DeepSeek Chat",
        api_base="https://api.deepseek.com/v1",
        api_key_env="DEEPSEEK_API_KEY",
        supports_json_mode=True,
        supports_structured_output=True,
        max_output_tokens=8192,
        is_local=False,
        max_context_tokens=64000,
        supports_long_context=True,
        cost_tier=CostTier.LOW,
        reasoning_score=7,
        creativity_score=6,
        latency_score=7,
    ),
}


def calculate_cost_single_model(
    model_name: str,
    profiles: dict[str, tuple[int, int, int]],
) -> dict[str, float]:
    costs: dict[str, float] = {}
    for task_type, (num_calls, prompt_tok, completion_tok) in profiles.items():
        total_prompt = num_calls * prompt_tok
        total_completion = num_calls * completion_tok
        costs[task_type] = estimate_cost_usd(total_prompt, total_completion, model_name)
    costs["total"] = sum(v for k, v in costs.items() if k != "total")
    return costs


def calculate_cost_routed(
    models: dict[str, ModelConfig],
    profiles: dict[str, tuple[int, int, int]],
) -> tuple[dict[str, float], dict[str, str]]:
    costs: dict[str, float] = {}
    selections: dict[str, str] = {}

    for task_type_str, (num_calls, prompt_tok, completion_tok) in profiles.items():
        tt = TaskType(task_type_str)
        selected_id = select_model(tt, models)
        if selected_id is None:
            selected_id = "openai:gpt-4o"

        model_cfg = models[selected_id]
        model_name = model_cfg.model_name
        selections[task_type_str] = f"{selected_id} ({model_name})"

        total_prompt = num_calls * prompt_tok
        total_completion = num_calls * completion_tok
        costs[task_type_str] = estimate_cost_usd(total_prompt, total_completion, model_name)

    costs["total"] = sum(v for k, v in costs.items() if k != "total")
    return costs, selections


def print_comparison(
    label: str,
    profiles: dict[str, tuple[int, int, int]],
    models: dict[str, ModelConfig],
) -> dict[str, float]:
    print(f"\n{'=' * 70}")
    print(f"  {label}")
    print(f"{'=' * 70}")

    total_calls = sum(n for n, _, _ in profiles.values())
    total_prompt = sum(n * p for n, p, _ in profiles.values())
    total_completion = sum(n * c for n, _, c in profiles.values())
    print(f"\n  Total LLM calls: {total_calls}")
    print(f"  Total prompt tokens: {total_prompt:,}")
    print(f"  Total completion tokens: {total_completion:,}")

    baseline = calculate_cost_single_model("gpt-4o", profiles)
    routed, selections = calculate_cost_routed(models, profiles)

    print(f"\n  {'Task Type':<15} {'Router Selection':<35} {'Calls':>5}")
    print(f"  {'-' * 55}")
    for task_type, (num_calls, _, _) in profiles.items():
        sel = selections.get(task_type, "N/A")
        print(f"  {task_type:<15} {sel:<35} {num_calls:>5}")

    print(f"\n  {'Task Type':<15} {'All gpt-4o':>12} {'Routed':>12} {'Savings':>10}")
    print(f"  {'-' * 50}")
    for task_type in profiles:
        b = baseline[task_type]
        r = routed[task_type]
        saving = ((b - r) / b * 100) if b > 0 else 0
        print(f"  {task_type:<15} ${b:>10.6f} ${r:>10.6f} {saving:>8.1f}%")

    b_total = baseline["total"]
    r_total = routed["total"]
    total_saving = ((b_total - r_total) / b_total * 100) if b_total > 0 else 0

    print(f"  {'-' * 50}")
    print(f"  {'TOTAL':<15} ${b_total:>10.6f} ${r_total:>10.6f} {total_saving:>8.1f}%")
    print(f"\n  Cost reduction: {total_saving:.1f}%")
    print(f"  Baseline cost:  ${b_total:.6f}")
    print(f"  Routed cost:    ${r_total:.6f}")
    print(f"  Saved:          ${b_total - r_total:.6f}")

    return {"baseline": b_total, "routed": r_total, "saving_pct": total_saving}


def print_pricing_reference():
    print(f"\n{'=' * 70}")
    print("  PRICING REFERENCE (USD per 1M tokens)")
    print(f"{'=' * 70}")
    print(f"\n  {'Model':<20} {'Input':>10} {'Output':>10}")
    print(f"  {'-' * 40}")
    for model, (inp, out) in sorted(PRICING_TABLE.items()):
        print(f"  {model:<20} ${inp:>8.2f} ${out:>8.2f}")


def print_router_decisions():
    print(f"\n{'=' * 70}")
    print("  ROUTER DECISION MATRIX")
    print(f"{'=' * 70}")

    print(f"\n  {'Task':<12} {'Requirements':<45} {'max_cost':>8}")
    print(f"  {'-' * 65}")
    for tt, req in TASK_REQUIREMENTS.items():
        flags = []
        if req.needs_reasoning:
            flags.append("reasoning")
        if req.needs_structured_output:
            flags.append("structured")
        if req.needs_long_context:
            flags.append("long_ctx")
        if req.prefers_creativity:
            flags.append("creative")
        if req.latency_sensitive:
            flags.append("low_latency")
        print(f"  {tt.value:<12} {', '.join(flags):<45} {req.max_cost_tier:>8}")

    print(f"\n  {'Task':<12} {'Model Scores':>60}")
    print(f"  {'-' * 72}")
    for tt in TaskType:
        scores = []
        for mid, mcfg in MODELS.items():
            s = _score_model(mcfg, tt)
            scores.append(f"{mid.split(':')[1]}={s:.1f}")
        selected = select_model(tt, MODELS)
        print(f"  {tt.value:<12} {', '.join(scores):<48} -> {selected}")


def main():
    print("\n" + "=" * 70)
    print("  AUTO-SCHOLAR COST ROUTING BENCHMARK")
    print("  Compares: all-gpt-4o baseline vs task-aware routing")
    print("=" * 70)

    print_pricing_reference()
    print_router_decisions()

    results_5 = print_comparison(
        "SCENARIO A: 5-Paper Literature Review",
        TASK_PROFILES_5_PAPERS,
        MODELS,
    )

    results_10 = print_comparison(
        "SCENARIO B: 10-Paper Literature Review",
        TASK_PROFILES_10_PAPERS,
        MODELS,
    )

    print(f"\n{'=' * 70}")
    print("  SUMMARY")
    print(f"{'=' * 70}")
    print(f"\n  5-paper review:  {results_5['saving_pct']:.1f}% cost reduction")
    print(f"  10-paper review: {results_10['saving_pct']:.1f}% cost reduction")
    avg_saving = (results_5["saving_pct"] + results_10["saving_pct"]) / 2
    print(f"  Average:         {avg_saving:.1f}% cost reduction")
    print(f"\n  Based on models.yaml config (gpt-4o + gpt-4o-mini + deepseek-chat)")
    print(f"  Router selects cheapest capable model per task type requirements.")
    print()


if __name__ == "__main__":
    main()
