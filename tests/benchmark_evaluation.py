#!/usr/bin/env python3
"""Benchmark script for the 7-dimension evaluation framework.

Run as: python tests/benchmark_evaluation.py
Or via pytest: pytest tests/benchmark_evaluation.py -v
"""

import time

import pytest

from backend.evaluation.academic_style import calculate_academic_style
from backend.evaluation.citation_metrics import (
    calculate_citation_precision,
    calculate_citation_recall,
)
from backend.evaluation.runner import run_evaluation
from backend.evaluation.section_completeness import evaluate_section_completeness
from backend.schemas import (
    ClaimVerificationSummary,
    DraftOutput,
    PaperMetadata,
    PaperSource,
    ReviewSection,
)


def create_sample_draft(num_sections: int = 5, citations_per_section: int = 3) -> DraftOutput:
    sections = []
    section_names = ["Introduction", "Background", "Methods", "Discussion", "Conclusion"]

    for i in range(num_sections):
        heading = section_names[i] if i < len(section_names) else f"Section {i + 1}"
        citations = " ".join(f"{{cite:{(j % 10) + 1}}}" for j in range(citations_per_section))
        content = f"This section discusses important findings. {citations} The results may suggest new directions. It appears that further research is needed. The data was analyzed carefully."
        sections.append(ReviewSection(heading=heading, content=content))

    return DraftOutput(title="Benchmark Review", sections=sections)


def create_sample_papers(num_papers: int = 10) -> list[PaperMetadata]:
    return [
        PaperMetadata(
            paper_id=f"paper_{i}",
            title=f"Paper {i}: A Study on Topic {i}",
            authors=[f"Author {i}A", f"Author {i}B"],
            abstract=f"This paper studies topic {i} in depth.",
            url=f"http://example.com/paper/{i}",
            year=2020 + (i % 5),
            source=PaperSource.SEMANTIC_SCHOLAR,
        )
        for i in range(1, num_papers + 1)
    ]


class TestBenchmarkEvaluation:
    @pytest.mark.slow
    def test_benchmark_citation_precision(self):
        draft = create_sample_draft(num_sections=10, citations_per_section=5)
        num_papers = 10

        start = time.perf_counter()
        iterations = 1000
        for _ in range(iterations):
            calculate_citation_precision(draft, num_papers)
        elapsed = time.perf_counter() - start

        avg_ms = (elapsed / iterations) * 1000
        print(f"\nCitation Precision: {avg_ms:.3f}ms per call ({iterations} iterations)")
        assert avg_ms < 10, f"Citation precision too slow: {avg_ms:.3f}ms"

    @pytest.mark.slow
    def test_benchmark_citation_recall(self):
        draft = create_sample_draft(num_sections=10, citations_per_section=5)
        papers = create_sample_papers(10)

        start = time.perf_counter()
        iterations = 1000
        for _ in range(iterations):
            calculate_citation_recall(draft, papers)
        elapsed = time.perf_counter() - start

        avg_ms = (elapsed / iterations) * 1000
        print(f"\nCitation Recall: {avg_ms:.3f}ms per call ({iterations} iterations)")
        assert avg_ms < 10, f"Citation recall too slow: {avg_ms:.3f}ms"

    @pytest.mark.slow
    def test_benchmark_section_completeness(self):
        draft = create_sample_draft(num_sections=10)

        start = time.perf_counter()
        iterations = 1000
        for _ in range(iterations):
            evaluate_section_completeness(draft, "en")
        elapsed = time.perf_counter() - start

        avg_ms = (elapsed / iterations) * 1000
        print(f"\nSection Completeness: {avg_ms:.3f}ms per call ({iterations} iterations)")
        assert avg_ms < 10, f"Section completeness too slow: {avg_ms:.3f}ms"

    @pytest.mark.slow
    def test_benchmark_academic_style(self):
        draft = create_sample_draft(num_sections=10, citations_per_section=5)

        start = time.perf_counter()
        iterations = 100
        for _ in range(iterations):
            calculate_academic_style(draft, "en")
        elapsed = time.perf_counter() - start

        avg_ms = (elapsed / iterations) * 1000
        print(f"\nAcademic Style: {avg_ms:.3f}ms per call ({iterations} iterations)")
        assert avg_ms < 50, f"Academic style too slow: {avg_ms:.3f}ms"

    @pytest.mark.slow
    def test_benchmark_full_evaluation(self):
        draft = create_sample_draft(num_sections=5, citations_per_section=3)
        papers = create_sample_papers(10)
        logs = [f"[node_{i}] completed in {i}.0s" for i in range(5)]
        claim_verification = ClaimVerificationSummary(
            total_claims=20,
            total_verifications=20,
            entails_count=16,
            insufficient_count=4,
            contradicts_count=0,
        )

        start = time.perf_counter()
        iterations = 100
        for _ in range(iterations):
            run_evaluation(
                thread_id="benchmark",
                draft=draft,
                approved_papers=papers,
                logs=logs,
                language="en",
                claim_verification=claim_verification,
            )
        elapsed = time.perf_counter() - start

        avg_ms = (elapsed / iterations) * 1000
        print(f"\nFull Evaluation: {avg_ms:.3f}ms per call ({iterations} iterations)")
        assert avg_ms < 100, f"Full evaluation too slow: {avg_ms:.3f}ms"


def run_benchmark():
    print("=" * 60)
    print("7-Dimension Evaluation Framework Benchmark")
    print("=" * 60)

    draft = create_sample_draft(num_sections=5, citations_per_section=3)
    papers = create_sample_papers(10)
    logs = [f"[node_{i}] completed in {i}.0s" for i in range(5)]
    claim_verification = ClaimVerificationSummary(
        total_claims=20,
        total_verifications=20,
        entails_count=16,
        insufficient_count=4,
        contradicts_count=0,
    )

    result = run_evaluation(
        thread_id="benchmark",
        draft=draft,
        approved_papers=papers,
        logs=logs,
        language="en",
        claim_verification=claim_verification,
    )

    print("\n--- Evaluation Results ---")
    print(f"Citation Precision: {result.citation_precision.precision:.1%}")
    print(f"Citation Recall: {result.citation_recall.recall:.1%}")
    print(f"Claim Support Rate: {result.claim_support_rate:.1%}")
    print(f"Section Completeness: {result.section_completeness.completeness_score:.1%}")
    print(f"Hedging Ratio: {result.academic_style.hedging_ratio:.1%}")
    print(f"Passive Ratio: {result.academic_style.passive_ratio:.1%}")
    print(f"Citation Density: {result.academic_style.citation_density:.2f} per 100 words")
    print(f"\nAutomated Score: {result.automated_score:.1%}")

    print("\n--- Performance Benchmark ---")
    iterations = 100

    start = time.perf_counter()
    for _ in range(iterations):
        calculate_citation_precision(draft, len(papers))
    print(f"Citation Precision: {((time.perf_counter() - start) / iterations) * 1000:.3f}ms")

    start = time.perf_counter()
    for _ in range(iterations):
        calculate_citation_recall(draft, papers)
    print(f"Citation Recall: {((time.perf_counter() - start) / iterations) * 1000:.3f}ms")

    start = time.perf_counter()
    for _ in range(iterations):
        evaluate_section_completeness(draft, "en")
    print(f"Section Completeness: {((time.perf_counter() - start) / iterations) * 1000:.3f}ms")

    start = time.perf_counter()
    for _ in range(iterations):
        calculate_academic_style(draft, "en")
    print(f"Academic Style: {((time.perf_counter() - start) / iterations) * 1000:.3f}ms")

    start = time.perf_counter()
    for _ in range(iterations):
        run_evaluation(
            thread_id="benchmark",
            draft=draft,
            approved_papers=papers,
            logs=logs,
            language="en",
            claim_verification=claim_verification,
        )
    print(f"Full Evaluation: {((time.perf_counter() - start) / iterations) * 1000:.3f}ms")

    print("\n" + "=" * 60)
    print("Benchmark Complete")
    print("=" * 60)


if __name__ == "__main__":
    run_benchmark()
