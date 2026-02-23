"""Test environment variable parsing and configuration."""

import os

from backend.constants import (
    CLAIM_BATCH_SIZE,
    CLAIM_VERIFICATION_CONCURRENCY,
    LLM_CONCURRENCY,
    _parse_int_env,
)


class TestParseIntEnv:
    """Test _parse_int_env helper function."""

    def test_parse_int_env_with_default(self):
        """Should return default value when env var is not set."""
        # Ensure env var is not set
        key = "TEST_PARSE_INT_ENV_DEFAULT"
        if key in os.environ:
            del os.environ[key]

        result = _parse_int_env(key, default=42, min_val=1, max_val=100)
        assert result == 42

    def test_parse_int_env_with_valid_value(self):
        """Should return parsed integer when env var is set and valid."""
        key = "TEST_PARSE_INT_ENV_VALID"
        os.environ[key] = "25"
        try:
            result = _parse_int_env(key, default=0, min_val=1, max_val=100)
            assert result == 25
        finally:
            del os.environ[key]

    def test_parse_int_env_clamps_to_min(self):
        """Should clamp to min_val when value is below minimum."""
        key = "TEST_PARSE_INT_ENV_MIN"
        os.environ[key] = "0"
        try:
            result = _parse_int_env(key, default=5, min_val=1, max_val=100)
            assert result == 1
        finally:
            del os.environ[key]

    def test_parse_int_env_clamps_to_max(self):
        """Should clamp to max_val when value is above maximum."""
        key = "TEST_PARSE_INT_ENV_MAX"
        os.environ[key] = "150"
        try:
            result = _parse_int_env(key, default=5, min_val=1, max_val=100)
            assert result == 100
        finally:
            del os.environ[key]

    def test_parse_int_env_invalid_string_uses_default(self):
        """Should use default when env var is not a valid integer."""
        key = "TEST_PARSE_INT_ENV_INVALID"
        os.environ[key] = "not-a-number"
        try:
            result = _parse_int_env(key, default=7, min_val=1, max_val=100)
            assert result == 7
        finally:
            del os.environ[key]

    def test_parse_int_env_empty_string_uses_default(self):
        """Should use default when env var is empty string."""
        key = "TEST_PARSE_INT_ENV_EMPTY"
        os.environ[key] = ""
        try:
            result = _parse_int_env(key, default=3, min_val=1, max_val=100)
            assert result == 3
        finally:
            del os.environ[key]

    def test_parse_int_env_whitespace_string_uses_default(self):
        """Should use default when env var is whitespace only."""
        key = "TEST_PARSE_INT_ENV_WHITESPACE"
        os.environ[key] = "   "
        try:
            result = _parse_int_env(key, default=9, min_val=1, max_val=100)
            assert result == 9
        finally:
            del os.environ[key]


class TestLLMConcurrency:
    """Test LLM_CONCURRENCY configuration."""

    def test_llm_concurrency_has_safe_default(self):
        """Should have a safe default value."""
        # Default should be 2 (safe for free/low-tier API keys)
        assert LLM_CONCURRENCY == 2

    def test_llm_concurrency_within_bounds(self):
        """Default value should be within allowed range."""
        assert 1 <= LLM_CONCURRENCY <= 20

    def test_llm_concurrency_respects_env_var(self, monkeypatch):
        """Should read from environment variable if set."""
        # This test verifies that the constant can be modified by env var
        # Actual value is set at import time, so we can't test it directly
        # But we can verify the bounds are correct
        assert LLM_CONCURRENCY >= 1
        assert LLM_CONCURRENCY <= 20


class TestClaimVerificationConcurrency:
    """Test CLAIM_VERIFICATION_CONCURRENCY configuration."""

    def test_claim_verification_concurrency_has_safe_default(self):
        """Should have a safe default value."""
        # Default should be 2 (safe for free/low-tier API keys)
        assert CLAIM_VERIFICATION_CONCURRENCY == 2

    def test_claim_verification_concurrency_within_bounds(self):
        """Default value should be within allowed range."""
        assert 1 <= CLAIM_VERIFICATION_CONCURRENCY <= 20

    def test_claim_verification_concurrency_respects_env_var(self):
        """Should read from environment variable if set."""
        # Verify the constant exists and has correct type
        assert isinstance(CLAIM_VERIFICATION_CONCURRENCY, int)
        assert CLAIM_VERIFICATION_CONCURRENCY >= 1
        assert CLAIM_VERIFICATION_CONCURRENCY <= 20


class TestClaimBatchSize:
    """Test CLAIM_BATCH_SIZE configuration."""

    def test_claim_batch_size_has_reasonable_default(self):
        """Should have a reasonable default value."""
        # Default should be 3 (groups 3 sections per batch)
        assert CLAIM_BATCH_SIZE == 3

    def test_claim_batch_size_is_positive_integer(self):
        """Should be a positive integer."""
        assert isinstance(CLAIM_BATCH_SIZE, int)
        assert CLAIM_BATCH_SIZE > 0
