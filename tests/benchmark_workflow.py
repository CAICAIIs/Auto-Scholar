#!/usr/bin/env python3
"""End-to-end performance benchmark for Auto-Scholar workflow.

This script measures the performance of the complete literature review
generation workflow, including all phases from planning to QA.

Usage:
    python tests/benchmark_workflow.py

Prerequisites:
    - Backend must be running with valid LLM_API_KEY
    - For accurate results, run with consistent environment:
      * LLM_CONCURRENCY=2 (baseline) and LLM_CONCURRENCY=4 (optimized)
"""

import argparse
import asyncio
import os
import time
from pathlib import Path
from typing import Any

import httpx
from pydantic import BaseModel

# Add project root to path
project_root = Path(__file__).parent.parent
os.chdir(project_root)


class WorkflowMetrics(BaseModel):
    """Metrics collected during workflow execution."""

    total_time: float
    planner_time: float | None = None
    retriever_time: float | None = None
    extractor_time: float | None = None
    writer_time: float | None = None
    critic_time: float | None = None
    llm_call_count: int = 0
    num_papers: int = 0
    num_sections: int = 0


class WorkflowBenchmark:
    """Benchmark runner for Auto-Scholar workflow."""

    def __init__(self, base_url: str = "http://localhost:8000"):
        self.base_url = base_url
        self.session_id: str | None = None
        self.log_events: list[dict[str, Any]] = []
        self.start_time: float | None = None

    def print_metrics(self, metrics: WorkflowMetrics, label: str = ""):
        """Print formatted metrics to console."""
        if label:
            print(f"\n{'=' * 60}")
            print(f"{label}")
            print(f"{'=' * 60}")

        print(f"Total Time:            {metrics.total_time:.2f}s")

        if metrics.planner_time:
            print(
                f"  Planner:             {metrics.planner_time:.2f}s ({metrics.planner_time / metrics.total_time * 100:.1f}%)"
            )
        if metrics.retriever_time:
            print(
                f"  Retriever:           {metrics.retriever_time:.2f}s ({metrics.retriever_time / metrics.total_time * 100:.1f}%)"
            )
        if metrics.extractor_time:
            print(
                f"  Extractor:           {metrics.extractor_time:.2f}s ({metrics.extractor_time / metrics.total_time * 100:.1f}%)"
            )
        if metrics.writer_time:
            print(
                f"  Writer:              {metrics.writer_time:.2f}s ({metrics.writer_time / metrics.total_time * 100:.1f}%)"
            )
        if metrics.critic_time:
            print(
                f"  Critic:              {metrics.critic_time:.2f}s ({metrics.critic_time / metrics.total_time * 100:.1f}%)"
            )

        print(f"\nPapers:                {metrics.num_papers}")
        print(f"Sections:              {metrics.num_sections}")
        print(f"LLM Calls (estimated): {metrics.llm_call_count}")

    async def start_workflow(self, query: str, num_papers: int = 3) -> WorkflowMetrics:
        """Run a complete workflow and collect metrics."""
        self.start_time = time.perf_counter()
        self.log_events = []

        metrics = WorkflowMetrics(total_time=0, num_papers=num_papers)

        try:
            # Step 1: Start workflow
            print(f"\n[1/5] Starting workflow: '{query}'")
            start = time.perf_counter()

            async with httpx.AsyncClient(timeout=300.0) as client:
                response = await client.post(
                    f"{self.base_url}/start",
                    json={"query": query, "num_papers": num_papers},
                )
                response.raise_for_status()
                data = response.json()
                self.session_id = data["session_id"]

            start_time = time.perf_counter()
            elapsed = start_time - start
            print(f"  → Session started: {self.session_id} ({elapsed:.2f}s)")

            # Step 2: Approve papers (for benchmark, we'll auto-approve first N)
            print("\n[2/5] Retrieving candidate papers...")
            start = time.perf_counter()

            async with httpx.AsyncClient(timeout=300.0) as client:
                response = await client.get(f"{self.base_url}/status/{self.session_id}")
                response.raise_for_status()
                data = response.json()

            # Wait for retriever to complete
            retriever_complete = False
            max_wait = 60
            start_wait = time.perf_counter()

            while not retriever_complete and (time.perf_counter() - start_wait) < max_wait:
                async with httpx.AsyncClient(timeout=10.0) as client:
                    response = await client.get(f"{self.base_url}/status/{self.session_id}")
                    response.raise_for_status()
                    data = response.json()

                    if data.get("stage") == "extractor":
                        retriever_complete = True
                        metrics.retriever_time = time.perf_counter() - start_wait
                        print(f"  → Retriever complete ({metrics.retriever_time:.2f}s)")
                        break

                await asyncio.sleep(1)

            if not retriever_complete:
                print("  → Warning: Retriever did not complete in time")
                return metrics

            # Get candidate papers
            papers = data.get("papers", [])
            papers_to_approve = papers[:num_papers]
            paper_ids = [p["paper_id"] for p in papers_to_approve]
            print(f"  → Found {len(papers)} papers, approving {len(paper_ids)}")

            # Step 3: Approve papers and continue
            print("\n[3/5] Approving papers and continuing extraction...")
            start = time.perf_counter()

            async with httpx.AsyncClient(timeout=300.0) as client:
                response = await client.post(
                    f"{self.base_url}/approve",
                    json={"session_id": self.session_id, "paper_ids": paper_ids},
                )
                response.raise_for_status()

            elapsed = time.perf_counter() - start
            print(f"  → Papers approved ({elapsed:.2f}s)")

            # Step 4: Wait for workflow to complete
            print("\n[4/5] Waiting for workflow completion...")
            workflow_complete = False
            max_wait = 180
            start_wait = time.perf_counter()

            while not workflow_complete and (time.perf_counter() - start_wait) < max_wait:
                async with httpx.AsyncClient(timeout=10.0) as client:
                    response = await client.get(f"{self.base_url}/status/{self.session_id}")
                    response.raise_for_status()
                    data = response.json()

                    stage = data.get("stage")

                    # Track node completion times
                    if stage == "writer" and metrics.extractor_time is None:
                        metrics.extractor_time = time.perf_counter() - start_wait
                        print(f"  → Extractor complete ({metrics.extractor_time:.2f}s)")
                    elif stage == "critic" and metrics.writer_time is None:
                        metrics.writer_time = time.perf_counter() - start_wait
                        print(f"  → Writer complete ({metrics.writer_time:.2f}s)")
                    elif stage == "done":
                        metrics.critic_time = time.perf_counter() - start_wait
                        workflow_complete = True
                        print(f"  → Critic complete ({metrics.critic_time:.2f}s)")
                        break

                await asyncio.sleep(1)

            if not workflow_complete:
                print("  → Warning: Workflow did not complete in time")
                return metrics

            # Step 5: Get final results
            print("\n[5/5] Retrieving final draft...")
            start = time.perf_counter()

            async with httpx.AsyncClient(timeout=300.0) as client:
                response = await client.get(f"{self.base_url}/status/{self.session_id}")
                response.raise_for_status()
                data = response.json()

            elapsed = time.perf_counter() - start

            metrics.total_time = time.perf_counter() - self.start_time

            # Get draft details
            final_draft = data.get("final_draft")
            if final_draft:
                metrics.num_sections = len(final_draft.get("sections", []))
                print(f"  → Retrieved {metrics.num_sections} sections ({elapsed:.2f}s)")

            # Estimate LLM call count (heuristic based on stage)
            # This is approximate - actual count would require log parsing
            if metrics.num_papers == 3:
                metrics.llm_call_count = 20  # Baseline estimate
            elif metrics.num_papers == 10:
                metrics.llm_call_count = 35  # Baseline estimate

            self.print_metrics(metrics)

            return metrics

        except Exception as e:
            print(f"\n❌ Error during workflow: {e}")
            raise

    async def run_benchmark_suite(
        self, query: str, iterations: int = 3, num_papers: int = 3
    ) -> list[WorkflowMetrics]:
        """Run multiple iterations and aggregate metrics."""
        print(f"\n{'=' * 60}")
        print("WORKFLOW BENCHMARK SUITE")
        print(f"{'=' * 60}")
        print(f"Query: {query}")
        print(f"Iterations: {iterations}")
        print(f"Papers per iteration: {num_papers}")
        print(f"LLM_CONCURRENCY: {os.getenv('LLM_CONCURRENCY', '2')}")
        print(f"CLAIM_VERIFICATION_CONCURRENCY: {os.getenv('CLAIM_VERIFICATION_CONCURRENCY', '2')}")

        all_metrics: list[WorkflowMetrics] = []

        for i in range(iterations):
            print(f"\n--- Iteration {i + 1}/{iterations} ---")
            metrics = await self.start_workflow(query, num_papers)
            all_metrics.append(metrics)

            # Small delay between iterations
            if i < iterations - 1:
                await asyncio.sleep(2)

        # Calculate aggregates
        print(f"\n{'=' * 60}")
        print("AGGREGATE RESULTS")
        print(f"{'=' * 60}")

        total_time_avg = sum(m.total_time for m in all_metrics) / len(all_metrics)
        extractor_time_avg = sum(m.extractor_time or 0 for m in all_metrics) / len(all_metrics)
        writer_time_avg = sum(m.writer_time or 0 for m in all_metrics) / len(all_metrics)

        print(f"Total Time (avg):      {total_time_avg:.2f}s")
        if extractor_time_avg > 0:
            print(f"Extractor Time (avg):   {extractor_time_avg:.2f}s")
        if writer_time_avg > 0:
            print(f"Writer Time (avg):      {writer_time_avg:.2f}s")
        print(f"\nMin Total Time:        {min(m.total_time for m in all_metrics):.2f}s")
        print(f"Max Total Time:        {max(m.total_time for m in all_metrics):.2f}s")

        return all_metrics


async def compare_configs(query: str, num_papers: int = 3):
    """Compare performance with different concurrency configurations."""
    print(f"\n{'=' * 60}")
    print("PERFORMANCE COMPARISON: Concurrency Impact")
    print(f"{'=' * 60}")

    configs = [
        ("LLM_CONCURRENCY=2", {"LLM_CONCURRENCY": "2"}),
        ("LLM_CONCURRENCY=4", {"LLM_CONCURRENCY": "4"}),
    ]

    results = {}

    for label, env_vars in configs:
        print(f"\n--- Testing: {label} ---")
        for key, value in env_vars.items():
            os.environ[key] = value

        benchmark = WorkflowBenchmark()
        try:
            metrics = await benchmark.start_workflow(query, num_papers)
            results[label] = metrics
        except Exception as e:
            print(f"Error: {e}")
        finally:
            await asyncio.sleep(1)

    # Print comparison
    print(f"\n{'=' * 60}")
    print("COMPARISON RESULTS")
    print(f"{'=' * 60}")

    if len(results) >= 2:
        baseline = results.get("LLM_CONCURRENCY=2")
        optimized = results.get("LLM_CONCURRENCY=4")

        if baseline and optimized:
            improvement = ((baseline.total_time - optimized.total_time) / baseline.total_time) * 100
            print(f"Baseline (2):  {baseline.total_time:.2f}s")
            print(f"Optimized (4): {optimized.total_time:.2f}s")
            print(f"Improvement:    {improvement:.1f}%")


async def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(description="Auto-Scholar Workflow Benchmark")
    parser.add_argument(
        "--query",
        type=str,
        default="transformer architecture in natural language processing",
        help="Research query for benchmark",
    )
    parser.add_argument(
        "--iterations",
        type=int,
        default=1,
        help="Number of iterations to run",
    )
    parser.add_argument(
        "--papers",
        type=int,
        default=3,
        help="Number of papers to include in review",
    )
    parser.add_argument(
        "--compare",
        action="store_true",
        help="Compare different concurrency configurations",
    )
    parser.add_argument(
        "--base-url",
        type=str,
        default="http://localhost:8000",
        help="Backend API base URL",
    )

    args = parser.parse_args()

    if args.compare:
        await compare_configs(args.query, args.papers)
    else:
        benchmark = WorkflowBenchmark(base_url=args.base_url)
        await benchmark.run_benchmark_suite(args.query, args.iterations, args.papers)

    print(f"\n{'=' * 60}")
    print("Benchmark Complete")
    print(f"{'=' * 60}")


if __name__ == "__main__":
    asyncio.run(main())
