#!/usr/bin/env python3
"""Diagnose timeout issues by testing LLM and API response times."""

import asyncio
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from dotenv import load_dotenv

load_dotenv()


async def test_llm():
    """Test LLM response time."""
    from backend.utils.llm_client import structured_completion
    from backend.nodes import KeywordPlan

    print("\n=== Testing LLM (DeepSeek) ===")
    print(f"Model: {os.environ.get('LLM_MODEL', 'not set')}")
    print(f"Base URL: {os.environ.get('LLM_BASE_URL', 'not set')}")

    start = time.perf_counter()
    try:
        result = await structured_completion(
            messages=[
                {
                    "role": "system",
                    "content": "Generate 3-5 search keywords for academic paper search.",
                },
                {"role": "user", "content": "machine learning for medical diagnosis"},
            ],
            response_model=KeywordPlan,
        )
        elapsed = time.perf_counter() - start
        print(f"✓ LLM responded in {elapsed:.2f}s")
        print(f"  Keywords: {result.keywords}")
        return True
    except Exception as e:
        elapsed = time.perf_counter() - start
        print(f"✗ LLM failed after {elapsed:.2f}s: {type(e).__name__}: {e}")
        return False


async def test_semantic_scholar():
    """Test Semantic Scholar API."""
    from backend.utils.scholar_api import search_semantic_scholar

    print("\n=== Testing Semantic Scholar API ===")
    start = time.perf_counter()
    try:
        papers = await search_semantic_scholar(["machine learning"], limit_per_query=5)
        elapsed = time.perf_counter() - start
        print(f"✓ Semantic Scholar responded in {elapsed:.2f}s")
        print(f"  Found {len(papers)} papers")
        return True
    except Exception as e:
        elapsed = time.perf_counter() - start
        print(f"✗ Semantic Scholar failed after {elapsed:.2f}s: {type(e).__name__}: {e}")
        return False


async def test_arxiv():
    """Test arXiv API."""
    from backend.utils.scholar_api import search_arxiv

    print("\n=== Testing arXiv API ===")
    start = time.perf_counter()
    try:
        papers = await search_arxiv(["machine learning"], limit_per_query=5)
        elapsed = time.perf_counter() - start
        print(f"✓ arXiv responded in {elapsed:.2f}s")
        print(f"  Found {len(papers)} papers")
        return True
    except Exception as e:
        elapsed = time.perf_counter() - start
        print(f"✗ arXiv failed after {elapsed:.2f}s: {type(e).__name__}: {e}")
        return False


async def test_full_workflow():
    """Test the full plan + search workflow."""
    from backend.nodes import planner_agent, retriever_agent
    from backend.schemas import PaperSource

    print("\n=== Testing Full Workflow (planner_agent + retriever_agent) ===")

    state = {
        "user_query": "machine learning for medical diagnosis",
        "is_continuation": False,
        "messages": [],
        "search_sources": [PaperSource.SEMANTIC_SCHOLAR],
    }

    total_start = time.perf_counter()

    print("\n--- planner_agent ---")
    start = time.perf_counter()
    try:
        plan_result = await planner_agent(state)
        elapsed = time.perf_counter() - start
        print(f"✓ planner_agent completed in {elapsed:.2f}s")
        print(f"  Keywords: {plan_result['search_keywords']}")
        if plan_result.get("research_plan"):
            rp = plan_result["research_plan"]
            print(f"  Sub-questions: {len(rp.sub_questions)}")
            print(f"  Reasoning: {rp.reasoning[:100]}...")
        state.update(plan_result)
    except Exception as e:
        elapsed = time.perf_counter() - start
        print(f"✗ planner_agent failed after {elapsed:.2f}s: {type(e).__name__}: {e}")
        return False

    print("\n--- retriever_agent ---")
    start = time.perf_counter()
    try:
        search_result = await retriever_agent(state)
        elapsed = time.perf_counter() - start
        print(f"✓ retriever_agent completed in {elapsed:.2f}s")
        print(f"  Found {len(search_result['candidate_papers'])} papers")
    except Exception as e:
        elapsed = time.perf_counter() - start
        print(f"✗ retriever_agent failed after {elapsed:.2f}s: {type(e).__name__}: {e}")
        return False

    total_elapsed = time.perf_counter() - total_start
    print(f"\n=== Total workflow time: {total_elapsed:.2f}s ===")

    if total_elapsed > 60:
        print("⚠ WARNING: Workflow took > 60s, may cause timeout issues")
    elif total_elapsed > 30:
        print("⚠ NOTICE: Workflow took > 30s, consider optimization")
    else:
        print("✓ Workflow completed in acceptable time")

    return True


async def main():
    print("=" * 60)
    print("Auto-Scholar Timeout Diagnostics")
    print("=" * 60)

    results = {}

    results["llm"] = await test_llm()
    results["semantic_scholar"] = await test_semantic_scholar()
    results["arxiv"] = await test_arxiv()
    results["full_workflow"] = await test_full_workflow()

    print("\n" + "=" * 60)
    print("Summary")
    print("=" * 60)
    for name, passed in results.items():
        status = "✓ PASS" if passed else "✗ FAIL"
        print(f"  {name}: {status}")

    from backend.utils.http_pool import close_session

    await close_session()


if __name__ == "__main__":
    asyncio.run(main())
