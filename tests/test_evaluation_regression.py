"""Evaluation regression tests with threshold assertions.

Runs on deterministic fixture data in CI (no @pytest.mark.slow).
Thresholds match proposal.md:
  - Citation precision ≥ 95%
  - Citation recall ≥ 80%
  - Section completeness = 100%
  - Hedging ratio 5-20%
  - Automated score > 0.7
"""

import pytest

from backend.evaluation.cost_tracker import reset_tracking
from backend.evaluation.runner import run_evaluation
from backend.schemas import (
    ClaimVerificationSummary,
    DraftOutput,
    PaperMetadata,
    PaperSource,
    ReviewSection,
)


@pytest.fixture(autouse=True)
def _clean_tracker():
    reset_tracking()
    yield
    reset_tracking()


def _make_papers(n: int) -> list[PaperMetadata]:
    return [
        PaperMetadata(
            paper_id=f"reg-{i}",
            title=f"Regression Paper {i}",
            authors=[f"Author {i}"],
            abstract=f"Abstract for paper {i}.",
            url=f"http://example.com/{i}",
            source=PaperSource.SEMANTIC_SCHOLAR,
        )
        for i in range(1, n + 1)
    ]


def _make_well_formed_draft(num_papers: int) -> DraftOutput:
    citations = " ".join(f"{{cite:{i}}}" for i in range(1, num_papers + 1))
    return DraftOutput(
        title="Regression Test Review",
        sections=[
            ReviewSection(
                heading="1. Introduction",
                content=(
                    f"Machine learning has revolutionized many fields {citations}. "
                    "Deep learning architectures achieve state-of-the-art results. "
                    "Neural networks process complex data representations. "
                    "This suggests new research directions. "
                    "Transfer learning enables knowledge reuse across domains. "
                    "The field was transformed by recent advances. "
                    "Convolutional networks excel at image recognition tasks. "
                    "Recurrent architectures handle sequential data effectively. "
                    "Attention mechanisms improve long-range dependencies. "
                    "Benchmark datasets provide standardized evaluation protocols."
                ),
            ),
            ReviewSection(
                heading="2. Background",
                content=(
                    f"Prior work has established key foundations {citations}. "
                    "Gradient descent optimizes model parameters iteratively. "
                    "Backpropagation computes gradients through network layers. "
                    "Results indicate significant progress in accuracy. "
                    "Regularization techniques prevent model overfitting. "
                    "The models were trained on large datasets. "
                    "Batch normalization accelerates training convergence. "
                    "Dropout randomly deactivates neurons during training. "
                    "Cross-validation estimates generalization performance. "
                    "Hyperparameter tuning affects final model quality."
                ),
            ),
            ReviewSection(
                heading="3. Methods",
                content=(
                    f"Various approaches have been proposed {citations}. "
                    "Transformer architectures use self-attention mechanisms. "
                    "Encoder-decoder structures handle sequence-to-sequence tasks. "
                    "The technique seems promising for real-world applications. "
                    "Pre-training on large corpora captures linguistic patterns. "
                    "Experiments were conducted across multiple benchmarks. "
                    "Fine-tuning adapts pre-trained models to specific tasks. "
                    "Multi-head attention captures diverse feature relationships. "
                    "Positional encodings preserve sequence order information. "
                    "Layer normalization stabilizes training dynamics."
                ),
            ),
            ReviewSection(
                heading="4. Discussion",
                content=(
                    f"The findings highlight important implications {citations}. "
                    "Performance was measured using standard metrics. "
                    "Ablation studies isolate individual component contributions. "
                    "Error analysis reveals systematic failure patterns. "
                    "Computational costs scale quadratically with sequence length. "
                    "The results were validated through cross-validation. "
                    "Model interpretability remains an open challenge. "
                    "Scaling laws predict performance from model size. "
                    "Hardware constraints limit practical deployment options. "
                    "Reproducibility requires careful experimental documentation."
                ),
            ),
            ReviewSection(
                heading="5. Conclusion",
                content=(
                    f"In summary, this review highlights key advances {citations}. "
                    "Future work may explore additional directions. "
                    "The contributions were recognized by the community. "
                    "Open-source implementations accelerate research progress. "
                    "Standardized benchmarks enable fair model comparison. "
                    "Interdisciplinary collaboration drives innovation forward. "
                    "Ethical considerations guide responsible AI development. "
                    "Data quality fundamentally determines model reliability. "
                    "Continuous evaluation ensures sustained model performance. "
                    "The field continues to evolve at a rapid pace."
                ),
            ),
        ],
    )


class TestEvaluationRegressionThresholds:
    def test_citation_precision_above_threshold(self):
        num_papers = 5
        draft = _make_well_formed_draft(num_papers)
        papers = _make_papers(num_papers)

        result = run_evaluation(
            thread_id="reg-precision",
            draft=draft,
            approved_papers=papers,
            logs=[],
            language="en",
        )
        assert result.citation_precision.precision >= 0.95, (
            f"Citation precision {result.citation_precision.precision:.1%} < 95% threshold"
        )

    def test_citation_recall_above_threshold(self):
        num_papers = 5
        draft = _make_well_formed_draft(num_papers)
        papers = _make_papers(num_papers)

        result = run_evaluation(
            thread_id="reg-recall",
            draft=draft,
            approved_papers=papers,
            logs=[],
            language="en",
        )
        assert result.citation_recall.recall >= 0.80, (
            f"Citation recall {result.citation_recall.recall:.1%} < 80% threshold"
        )

    def test_section_completeness_full(self):
        num_papers = 3
        draft = _make_well_formed_draft(num_papers)
        papers = _make_papers(num_papers)

        result = run_evaluation(
            thread_id="reg-sections",
            draft=draft,
            approved_papers=papers,
            logs=[],
            language="en",
        )
        assert result.section_completeness.completeness_score == 1.0, (
            f"Missing sections: {result.section_completeness.missing_sections}"
        )

    def test_hedging_ratio_in_range(self):
        num_papers = 3
        draft = _make_well_formed_draft(num_papers)
        papers = _make_papers(num_papers)

        result = run_evaluation(
            thread_id="reg-hedging",
            draft=draft,
            approved_papers=papers,
            logs=[],
            language="en",
        )
        ratio = result.academic_style.hedging_ratio
        assert 0.05 <= ratio <= 0.20, f"Hedging ratio {ratio:.1%} outside 5-20% range"

    def test_automated_score_above_threshold(self):
        num_papers = 5
        draft = _make_well_formed_draft(num_papers)
        papers = _make_papers(num_papers)
        claim_verification = ClaimVerificationSummary(
            total_claims=10,
            total_verifications=10,
            entails_count=9,
            insufficient_count=1,
            contradicts_count=0,
        )

        result = run_evaluation(
            thread_id="reg-score",
            draft=draft,
            approved_papers=papers,
            logs=[],
            language="en",
            claim_verification=claim_verification,
        )
        assert result.automated_score > 0.70, (
            f"Automated score {result.automated_score:.1%} <= 70% threshold"
        )

    def test_chinese_section_completeness(self):
        num_papers = 3
        citations = " ".join(f"{{cite:{i}}}" for i in range(1, num_papers + 1))
        draft = DraftOutput(
            title="中文回归测试综述",
            sections=[
                ReviewSection(heading="引言", content=f"机器学习可能改变许多领域 {citations}。"),
                ReviewSection(heading="背景", content=f"先前的工作奠定了基础 {citations}。"),
                ReviewSection(heading="方法", content=f"提出了多种方法 {citations}。"),
                ReviewSection(heading="讨论", content=f"结果表明了重要意义 {citations}。"),
                ReviewSection(heading="结论", content=f"总之，本综述强调了关键进展 {citations}。"),
            ],
        )
        papers = _make_papers(num_papers)

        result = run_evaluation(
            thread_id="reg-zh",
            draft=draft,
            approved_papers=papers,
            logs=[],
            language="zh",
        )
        assert result.section_completeness.completeness_score == 1.0

    def test_cost_efficiency_tracks_node_timings_from_logs(self):
        num_papers = 3
        draft = _make_well_formed_draft(num_papers)
        papers = _make_papers(num_papers)
        logs = [
            "[planner_agent] completed in 1.5s",
            "[retriever_agent] completed in 8.0s",
            "[writer_agent] completed in 3.0s",
        ]

        result = run_evaluation(
            thread_id="reg-cost",
            draft=draft,
            approved_papers=papers,
            logs=logs,
            language="en",
        )
        assert result.cost_efficiency.total_latency_ms > 0
        assert len(result.cost_efficiency.node_timings) >= 3

    def test_full_regression_suite(self):
        num_papers = 5
        draft = _make_well_formed_draft(num_papers)
        papers = _make_papers(num_papers)
        claim_verification = ClaimVerificationSummary(
            total_claims=15,
            total_verifications=15,
            entails_count=13,
            insufficient_count=2,
            contradicts_count=0,
        )
        logs = [
            "[planner_agent] completed in 1.0s",
            "[retriever_agent] completed in 5.0s",
            "[extractor_agent] completed in 4.0s",
            "[writer_agent] completed in 3.0s",
            "[critic_agent] completed in 0.5s",
        ]

        result = run_evaluation(
            thread_id="reg-full",
            draft=draft,
            approved_papers=papers,
            logs=logs,
            language="en",
            claim_verification=claim_verification,
        )

        assert result.citation_precision.precision >= 0.95
        assert result.citation_recall.recall >= 0.80
        assert result.section_completeness.completeness_score == 1.0
        assert 0.05 <= result.academic_style.hedging_ratio <= 0.20
        assert result.automated_score > 0.70
        assert result.cost_efficiency.total_latency_ms > 0
        assert result.claim_support_rate >= 0.80
        assert result.paper_count == num_papers
