from backend.schemas import CostTier, ModelProvider
from backend.utils.llm_client import _infer_capabilities


class TestInferCapabilities:
    def test_ollama_is_cheap_and_fast(self):
        caps = _infer_capabilities(ModelProvider.OLLAMA, "llama3.1:8b")
        assert caps["cost_tier"] == CostTier.LOW
        assert caps["latency_score"] == 8
        assert caps["supports_long_context"] is False
        assert caps["max_context_tokens"] == 8_000

    def test_deepseek_chat_defaults(self):
        caps = _infer_capabilities(ModelProvider.DEEPSEEK, "deepseek-chat")
        assert caps["cost_tier"] == CostTier.LOW
        assert caps["supports_long_context"] is True
        assert caps["reasoning_score"] == 7

    def test_deepseek_reasoner_high_reasoning(self):
        caps = _infer_capabilities(ModelProvider.DEEPSEEK, "deepseek-reasoner")
        assert caps["reasoning_score"] == 9

    def test_deepseek_r1_high_reasoning(self):
        caps = _infer_capabilities(ModelProvider.DEEPSEEK, "deepseek-r1-lite")
        assert caps["reasoning_score"] == 9

    def test_openai_gpt4o_defaults(self):
        caps = _infer_capabilities(ModelProvider.OPENAI, "gpt-4o")
        assert caps["cost_tier"] == CostTier.HIGH
        assert caps["max_context_tokens"] == 128_000
        assert caps["supports_long_context"] is True
        assert caps["reasoning_score"] == 8
        assert caps["creativity_score"] == 8

    def test_openai_mini_is_cheap_and_fast(self):
        caps = _infer_capabilities(ModelProvider.OPENAI, "gpt-4o-mini")
        assert caps["cost_tier"] == CostTier.LOW
        assert caps["latency_score"] == 9
        assert caps["reasoning_score"] == 6
        assert caps["creativity_score"] == 5

    def test_openai_o1_high_reasoning(self):
        caps = _infer_capabilities(ModelProvider.OPENAI, "o1-preview")
        assert caps["reasoning_score"] == 9

    def test_openai_o3_high_reasoning(self):
        caps = _infer_capabilities(ModelProvider.OPENAI, "o3-mini")
        assert caps["reasoning_score"] == 9
        assert caps["cost_tier"] == CostTier.LOW

    def test_custom_provider_uses_openai_defaults(self):
        caps = _infer_capabilities(ModelProvider.CUSTOM, "some-model")
        assert caps["max_context_tokens"] == 128_000
        assert caps["cost_tier"] == CostTier.HIGH


class TestCostTier:
    def test_ordering(self):
        assert CostTier.LOW < CostTier.MEDIUM < CostTier.HIGH

    def test_values(self):
        assert CostTier.LOW == 1
        assert CostTier.MEDIUM == 2
        assert CostTier.HIGH == 3
