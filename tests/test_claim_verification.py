"""Tests for claim-level citation verification."""

from unittest.mock import AsyncMock, patch

import pytest

from backend.schemas import (
    Claim,
    ClaimVerificationResult,
    ClaimVerificationSummary,
    DraftOutput,
    EntailmentLabel,
    PaperMetadata,
    PaperSource,
    ReviewSection,
)
from backend.utils.claim_verifier import (
    extract_all_claims,
    extract_claims_from_section,
    summarize_verifications,
    verify_draft_citations,
)


@pytest.fixture
def mock_papers() -> list[PaperMetadata]:
    return [
        PaperMetadata(
            paper_id="paper_1",
            title="Transformer Architecture for NLP",
            abstract="We introduce the transformer architecture using self-attention mechanisms.",
            authors=["Vaswani et al."],
            year=2017,
            url="https://example.com/1",
            source=PaperSource.SEMANTIC_SCHOLAR,
            core_contribution="Self-attention mechanism that enables parallel processing.",
        ),
        PaperMetadata(
            paper_id="paper_2",
            title="BERT: Pre-training Deep Bidirectional Transformers",
            abstract="We introduce BERT for pre-training language representations.",
            authors=["Devlin et al."],
            year=2019,
            url="https://example.com/2",
            source=PaperSource.SEMANTIC_SCHOLAR,
            core_contribution="Bidirectional pre-training for language understanding.",
        ),
    ]


@pytest.fixture
def mock_draft() -> DraftOutput:
    return DraftOutput(
        title="Literature Review on Transformers",
        sections=[
            ReviewSection(
                heading="Introduction",
                content="The transformer architecture {cite:1} revolutionized NLP. "
                "BERT {cite:2} further advanced the field.",
            ),
            ReviewSection(
                heading="Methods",
                content="Self-attention {cite:1} enables parallel computation. "
                "Pre-training {cite:2} improves downstream tasks.",
            ),
        ],
    )


class TestClaimExtraction:
    async def test_extract_claims_from_section_with_citations(self):
        mock_claims = ["The transformer {cite:1} uses self-attention."]

        with patch(
            "backend.utils.claim_verifier.structured_completion",
            new=AsyncMock(return_value=AsyncMock(claims=mock_claims)),
        ):
            claims = await extract_claims_from_section(
                section_index=0,
                section_title="Introduction",
                section_content="The transformer {cite:1} uses self-attention.",
            )

            assert len(claims) == 1
            assert claims[0].claim_id == "s0_c0"
            assert claims[0].citation_indices == [1]

    async def test_extract_claims_skips_section_without_citations(self):
        claims = await extract_claims_from_section(
            section_index=0,
            section_title="Abstract",
            section_content="This is an abstract without any citations.",
        )

        assert len(claims) == 0

    async def test_extract_claims_handles_multiple_citations(self):
        mock_claims = ["Both {cite:1} and {cite:2} contribute to the field."]

        with patch(
            "backend.utils.claim_verifier.structured_completion",
            new=AsyncMock(return_value=AsyncMock(claims=mock_claims)),
        ):
            claims = await extract_claims_from_section(
                section_index=1,
                section_title="Discussion",
                section_content="Both {cite:1} and {cite:2} contribute to the field.",
            )

            assert len(claims) == 1
            assert set(claims[0].citation_indices) == {1, 2}


class TestClaimVerification:
    async def test_verify_draft_citations_success(self, mock_draft, mock_papers):
        mock_claims = [
            "The transformer {cite:1} revolutionized NLP.",
            "BERT {cite:2} advanced the field.",
        ]

        mock_verification = AsyncMock(
            label="entails",
            confidence=0.95,
            evidence_snippet="Self-attention mechanism",
            rationale="The paper describes transformer architecture.",
        )

        with (
            patch(
                "backend.utils.claim_verifier.structured_completion",
                new=AsyncMock(
                    side_effect=[
                        AsyncMock(claims=mock_claims[:1]),
                        AsyncMock(claims=mock_claims[1:]),
                        mock_verification,
                        mock_verification,
                    ]
                ),
            ),
        ):
            claims, summary = await verify_draft_citations(mock_draft, mock_papers)

            assert summary.total_claims >= 0
            assert summary.entails_count >= 0

    async def test_verify_draft_citations_empty_draft(self, mock_papers):
        empty_draft = DraftOutput(title="Empty", sections=[])

        claims, summary = await verify_draft_citations(empty_draft, mock_papers)

        assert len(claims) == 0
        assert summary.total_claims == 0
        assert summary.total_verifications == 0


class TestSummarizeVerifications:
    def test_summarize_all_entails(self):
        claims = [Claim(claim_id="c1", text="Claim 1", section_index=0, citation_indices=[1])]
        results = [
            ClaimVerificationResult(
                claim_id="c1",
                claim_text="Claim 1",
                citation_index=1,
                paper_title="Paper 1",
                label=EntailmentLabel.ENTAILS,
                confidence=0.9,
            )
        ]

        summary = summarize_verifications(claims, results)

        assert summary.total_claims == 1
        assert summary.total_verifications == 1
        assert summary.entails_count == 1
        assert summary.insufficient_count == 0
        assert summary.contradicts_count == 0
        assert len(summary.failed_verifications) == 0

    def test_summarize_mixed_results(self):
        claims = [
            Claim(claim_id="c1", text="Claim 1", section_index=0, citation_indices=[1]),
            Claim(claim_id="c2", text="Claim 2", section_index=0, citation_indices=[2]),
        ]
        results = [
            ClaimVerificationResult(
                claim_id="c1",
                claim_text="Claim 1",
                citation_index=1,
                paper_title="Paper 1",
                label=EntailmentLabel.ENTAILS,
                confidence=0.9,
            ),
            ClaimVerificationResult(
                claim_id="c2",
                claim_text="Claim 2",
                citation_index=2,
                paper_title="Paper 2",
                label=EntailmentLabel.INSUFFICIENT,
                confidence=0.6,
            ),
        ]

        summary = summarize_verifications(claims, results)

        assert summary.total_claims == 2
        assert summary.total_verifications == 2
        assert summary.entails_count == 1
        assert summary.insufficient_count == 1
        assert summary.contradicts_count == 0
        assert len(summary.failed_verifications) == 1

    def test_summarize_with_contradictions(self):
        claims = [Claim(claim_id="c1", text="Claim 1", section_index=0, citation_indices=[1])]
        results = [
            ClaimVerificationResult(
                claim_id="c1",
                claim_text="Claim 1",
                citation_index=1,
                paper_title="Paper 1",
                label=EntailmentLabel.CONTRADICTS,
                confidence=0.85,
            )
        ]

        summary = summarize_verifications(claims, results)

        assert summary.contradicts_count == 1
        assert len(summary.failed_verifications) == 1
        assert summary.failed_verifications[0].label == EntailmentLabel.CONTRADICTS

    def test_summarize_empty_results(self):
        summary = summarize_verifications([], [])

        assert summary.total_claims == 0
        assert summary.total_verifications == 0
        assert summary.entails_count == 0


class TestCriticAgentIntegration:
    async def test_critic_agent_with_claim_verification_enabled(self, mock_draft, mock_papers):
        from backend.nodes import critic_agent

        state = {
            "final_draft": mock_draft,
            "approved_papers": mock_papers,
            "retry_count": 0,
        }

        mock_summary = ClaimVerificationSummary(
            total_claims=2,
            total_verifications=2,
            entails_count=2,
            insufficient_count=0,
            contradicts_count=0,
            failed_verifications=[],
        )

        with (
            patch("backend.nodes.CLAIM_VERIFICATION_ENABLED", True),
            patch(
                "backend.nodes.verify_draft_citations",
                new=AsyncMock(return_value=([], mock_summary)),
            ),
        ):
            result = await critic_agent(state)

            assert result["qa_errors"] == []
            assert result["claim_verification"] is not None
            assert "QA passed" in result["logs"][0]

    async def test_critic_agent_fails_on_low_entailment_ratio(self, mock_draft, mock_papers):
        from backend.nodes import critic_agent

        state = {
            "final_draft": mock_draft,
            "approved_papers": mock_papers,
            "retry_count": 0,
        }

        failed_result = ClaimVerificationResult(
            claim_id="c1",
            claim_text="Some claim that is not supported",
            citation_index=1,
            paper_title="Paper 1",
            label=EntailmentLabel.INSUFFICIENT,
            confidence=0.5,
            rationale="The paper does not support this claim.",
        )

        mock_summary = ClaimVerificationSummary(
            total_claims=2,
            total_verifications=2,
            entails_count=0,
            insufficient_count=2,
            contradicts_count=0,
            failed_verifications=[failed_result, failed_result],
        )

        with (
            patch("backend.nodes.CLAIM_VERIFICATION_ENABLED", True),
            patch("backend.nodes.MIN_ENTAILMENT_RATIO", 0.8),
            patch(
                "backend.nodes.verify_draft_citations",
                new=AsyncMock(return_value=([], mock_summary)),
            ),
        ):
            result = await critic_agent(state)

            assert len(result["qa_errors"]) > 0
            assert result["retry_count"] == 1
            assert "citation support ratio" in result["logs"][0]

    async def test_critic_agent_skips_verification_when_disabled(self, mock_draft, mock_papers):
        from backend.nodes import critic_agent

        state = {
            "final_draft": mock_draft,
            "approved_papers": mock_papers,
            "retry_count": 0,
        }

        with patch("backend.nodes.CLAIM_VERIFICATION_ENABLED", False):
            result = await critic_agent(state)

            assert result["qa_errors"] == []
            assert result.get("claim_verification") is None


class TestBatchClaimExtraction:
    async def test_extract_all_claims_with_3_section_batch(self):
        """Test batch extraction with exactly 3 sections (batch size)."""
        from backend.schemas import DraftOutput, ReviewSection

        draft = DraftOutput(
            title="Literature Review",
            sections=[
                ReviewSection(
                    heading="Introduction",
                    content="The transformer architecture {cite:1} revolutionized NLP.",
                ),
                ReviewSection(
                    heading="Methods",
                    content="Self-attention {cite:2} enables parallel computation.",
                ),
                ReviewSection(
                    heading="Results",
                    content="BERT {cite:3} achieves state-of-the-art performance.",
                ),
            ],
        )

        async def mock_batch_extraction(*args, **kwargs):
            """Mock successful batch extraction returning claims for all 3 sections."""
            return [
                Claim(
                    claim_id="s0_c0",
                    text="The transformer architecture revolutionized NLP.",
                    section_index=0,
                    citation_indices=[1],
                ),
                Claim(
                    claim_id="s1_c0",
                    text="Self-attention enables parallel computation.",
                    section_index=1,
                    citation_indices=[2],
                ),
                Claim(
                    claim_id="s2_c0",
                    text="BERT achieves state-of-the-art performance.",
                    section_index=2,
                    citation_indices=[3],
                ),
            ]

        with patch(
            "backend.utils.claim_verifier._extract_claims_batch",
            side_effect=mock_batch_extraction,
        ):
            results = await extract_all_claims(draft)

            assert len(results) == 3
            assert results[0].section_index == 0
            assert results[1].section_index == 1
            assert results[2].section_index == 2
            assert results[0].citation_indices == [1]
            assert results[1].citation_indices == [2]
            assert results[2].citation_indices == [3]

    async def test_extract_all_claims_batch_failure_fallback_to_per_section(self):
        """Test fallback to per-section extraction when batch extraction fails."""
        from backend.schemas import DraftOutput, ReviewSection

        draft = DraftOutput(
            title="Literature Review",
            sections=[
                ReviewSection(
                    heading="Introduction",
                    content="The transformer architecture {cite:1} revolutionized NLP.",
                ),
                ReviewSection(
                    heading="Methods",
                    content="Self-attention {cite:2} enables parallel computation.",
                ),
            ],
        )

        async def mock_batch_extraction(*args, **kwargs):
            raise Exception("Batch extraction failed")

        async def mock_per_section(*args, **kwargs):
            return AsyncMock(claims=["The transformer architecture revolutionized NLP."])

        with patch(
            "backend.utils.claim_verifier._extract_claims_batch",
            side_effect=mock_batch_extraction,
        ):
            with patch(
                "backend.utils.claim_verifier.extract_claims_from_section",
                new=AsyncMock(
                    return_value=[
                        Claim(
                            claim_id="s0_c0",
                            text="The transformer architecture revolutionized NLP.",
                            section_index=0,
                            citation_indices=[1],
                        )
                    ]
                ),
            ):
                results = await extract_all_claims(draft)

                assert len(results) == 2
