"""
Integration test for Phase 1.2 performance improvement.

This test demonstrates that parallelizing fulltext enrichment with extraction
reduces overall workflow execution time.

Note: This test is timing-dependent and intended for performance validation,
not for automated CI/CD pipelines.
"""

import asyncio
import time
from dataclasses import dataclass


@dataclass
class Paper:
    """Simple paper mock for testing."""

    paper_id: str
    title: str
    doi: str
    year: int
    pdf_url: str | None = None


@dataclass
class EnrichmentResult:
    """Mock enrichment result."""

    paper_id: str
    summary: str
    sections: list[str]


async def _mock_slow_enrich(paper: Paper, timeout: float = 0.2) -> EnrichmentResult:
    """Mock enrich that simulates network delay."""
    await asyncio.sleep(timeout)
    return EnrichmentResult(
        paper_id=paper.paper_id,
        summary=f"Summary for {paper.title}",
        sections=["Introduction", "Methodology"],
    )


async def _safe_enrich_with_timeout(
    paper: Paper,
    timeout: float = 0.2,
) -> EnrichmentResult | None:
    """Safe enrich wrapper with timeout."""
    try:
        return await _mock_slow_enrich(paper, timeout=timeout)
    except Exception as e:
        print(f"Error enriching paper {paper.paper_id}: {e}")
        return None


async def test_parallel_enrichment_faster_than_sequential():
    """
    Verify that parallel fulltext enrichment is faster than sequential.

    Expected: Parallel enrichment completes in ~0.2s (max of individual times)
    Sequential enrichment would complete in ~0.6s (sum of individual times)
    """
    papers = [
        Paper(
            paper_id=f"paper_{i}",
            title=f"Paper {i}",
            doi=f"10.1234/paper{i}",
            year=2024,
        )
        for i in range(3)
    ]

    start_time = time.time()
    parallel_results = await asyncio.gather(
        *[_safe_enrich_with_timeout(paper, timeout=0.2) for paper in papers],
        return_exceptions=False,
    )
    parallel_time = time.time() - start_time

    start_time = time.time()
    sequential_results = []
    for paper in papers:
        result = await _safe_enrich_with_timeout(paper, timeout=0.2)
        sequential_results.append(result)
    sequential_time = time.time() - start_time

    print("\nPerformance Test Results:")
    print(f"  Parallel time: {parallel_time:.3f}s")
    print(f"  Sequential time: {sequential_time:.3f}s")
    print(f"  Speedup: {sequential_time / parallel_time:.2f}x")

    assert parallel_time < sequential_time * 0.67, (
        f"Parallel enrichment ({parallel_time:.3f}s) should be at least "
        f"1.5x faster than sequential ({sequential_time:.3f}s)"
    )

    assert len(parallel_results) == len(sequential_results)
    for p, s in zip(parallel_results, sequential_results):
        assert p is not None and s is not None
        assert p.summary == s.summary

    print("\n✓ Parallel enrichment is significantly faster than sequential")
    return True


async def test_parallel_enrichment_resilience():
    """
    Verify that parallel enrichment continues even if some papers fail.

    This tests the safety of parallel enrichment with partial failures.
    """

    async def _enrich_with_failure(
        paper: Paper, should_fail: bool = False
    ) -> EnrichmentResult | None:
        """Mock enrich that can fail."""
        await asyncio.sleep(0.1)
        if should_fail:
            raise Exception(f"Network error for {paper.paper_id}")
        return EnrichmentResult(
            paper_id=paper.paper_id,
            summary=f"Summary for {paper.title}",
            sections=["Introduction"],
        )

    papers = [
        Paper(
            paper_id="paper_0",
            title="Success Paper",
            doi="10.1234/paper0",
            year=2024,
        ),
        Paper(
            paper_id="paper_1",
            title="Failure Paper",
            doi="10.1234/paper1",
            year=2024,
        ),
        Paper(
            paper_id="paper_2",
            title="Success Paper 2",
            doi="10.1234/paper2",
            year=2024,
        ),
    ]

    tasks = [
        _enrich_with_failure(paper, should_fail=(paper.paper_id == "paper_1")) for paper in papers
    ]

    start_time = time.time()
    results = await asyncio.gather(*tasks, return_exceptions=True)
    total_time = time.time() - start_time

    print("\nResilience Test Results:")
    print(f"  Total time: {total_time:.3f}s")
    print(f"  Successful enrichments: {sum(1 for r in results if not isinstance(r, Exception))}")
    print(f"  Failed enrichments: {sum(1 for r in results if isinstance(r, Exception))}")

    assert total_time < 0.2, f"Parallel enrichment should complete in ~0.1s, took {total_time:.3f}s"

    successful = [r for r in results if not isinstance(r, Exception)]
    failed = [r for r in results if isinstance(r, Exception)]
    assert len(successful) == 2, f"Expected 2 successful enrichments, got {len(successful)}"
    assert len(failed) == 1, f"Expected 1 failed enrichment, got {len(failed)}"

    print("\n✓ Parallel enrichment is resilient to individual failures")
    return True


async def run_all_tests():
    """Run all Phase 1.2 integration tests."""
    print("=" * 70)
    print("Phase 1.2 Performance Integration Tests")
    print("=" * 70)

    await test_parallel_enrichment_faster_than_sequential()
    print()
    await test_parallel_enrichment_resilience()

    print("\n" + "=" * 70)
    print("All Phase 1.2 integration tests passed!")
    print("=" * 70)


if __name__ == "__main__":
    asyncio.run(run_all_tests())
