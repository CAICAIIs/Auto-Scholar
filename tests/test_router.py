from backend.llm.router import _score_model, get_fallback_chain, select_model
from backend.llm.task_types import TaskType
from backend.schemas import CostTier, ModelConfig, ModelProvider


def _make_model(
    model_id: str = "openai:gpt-4o",
    provider: ModelProvider = ModelProvider.OPENAI,
    cost_tier: CostTier = CostTier.HIGH,
    reasoning_score: int = 8,
    creativity_score: int = 8,
    latency_score: int = 6,
    supports_structured_output: bool = True,
    supports_long_context: bool = True,
    enabled: bool = True,
) -> ModelConfig:
    return ModelConfig(
        id=model_id,
        provider=provider,
        model_name=model_id.split(":")[-1],
        display_name=model_id,
        api_base="https://api.openai.com/v1",
        cost_tier=cost_tier,
        reasoning_score=reasoning_score,
        creativity_score=creativity_score,
        latency_score=latency_score,
        supports_structured_output=supports_structured_output,
        supports_long_context=supports_long_context,
        enabled=enabled,
    )


def _multi_model_registry() -> dict[str, ModelConfig]:
    return {
        "openai:gpt-4o": _make_model(
            "openai:gpt-4o",
            cost_tier=CostTier.HIGH,
            reasoning_score=8,
            creativity_score=8,
            latency_score=6,
        ),
        "openai:gpt-4o-mini": _make_model(
            "openai:gpt-4o-mini",
            cost_tier=CostTier.LOW,
            reasoning_score=6,
            creativity_score=5,
            latency_score=9,
        ),
        "deepseek:deepseek-chat": _make_model(
            "deepseek:deepseek-chat",
            provider=ModelProvider.DEEPSEEK,
            cost_tier=CostTier.LOW,
            reasoning_score=7,
            creativity_score=6,
            latency_score=7,
        ),
        "ollama:llama3": _make_model(
            "ollama:llama3",
            provider=ModelProvider.OLLAMA,
            cost_tier=CostTier.LOW,
            reasoning_score=4,
            creativity_score=4,
            latency_score=8,
            supports_structured_output=False,
            supports_long_context=False,
        ),
    }


class TestSelectModel:
    def test_override_takes_precedence(self):
        registry = _multi_model_registry()
        result = select_model(TaskType.PLANNING, registry, override_model_id="ollama:llama3")
        assert result == "ollama:llama3"

    def test_override_unknown_id_falls_through_to_routing(self):
        registry = _multi_model_registry()
        result = select_model(TaskType.PLANNING, registry, override_model_id="nonexistent:model")
        assert result is not None
        assert result != "nonexistent:model"

    def test_planning_prefers_high_reasoning(self):
        registry = _multi_model_registry()
        result = select_model(TaskType.PLANNING, registry)
        assert result == "openai:gpt-4o"

    def test_extraction_prefers_fast_and_cheap(self):
        registry = _multi_model_registry()
        result = select_model(TaskType.EXTRACTION, registry)
        assert result in ("openai:gpt-4o-mini", "deepseek:deepseek-chat")

    def test_extraction_excludes_no_structured_output(self):
        registry = _multi_model_registry()
        result = select_model(TaskType.EXTRACTION, registry)
        assert result != "ollama:llama3"

    def test_writing_prefers_creative(self):
        registry = _multi_model_registry()
        result = select_model(TaskType.WRITING, registry)
        assert result == "openai:gpt-4o"

    def test_writing_excludes_no_long_context(self):
        registry = _multi_model_registry()
        result = select_model(TaskType.WRITING, registry)
        assert result != "ollama:llama3"

    def test_qa_prefers_cheap_and_fast(self):
        registry = _multi_model_registry()
        result = select_model(TaskType.QA, registry)
        assert result in ("openai:gpt-4o-mini", "deepseek:deepseek-chat")

    def test_empty_registry_returns_none(self):
        result = select_model(TaskType.PLANNING, {})
        assert result is None

    def test_all_disabled_returns_none(self):
        registry = {
            "m1": _make_model("m1", enabled=False),
        }
        result = select_model(TaskType.PLANNING, registry)
        assert result is None

    def test_single_model_always_selected_when_eligible(self):
        registry = {"only": _make_model("only", cost_tier=CostTier.LOW)}
        for task_type in TaskType:
            result = select_model(task_type, registry)
            assert result == "only"

    def test_cost_filter_excludes_expensive_for_qa(self):
        registry = {
            "expensive": _make_model("expensive", cost_tier=CostTier.HIGH),
        }
        result = select_model(TaskType.QA, registry)
        assert result is None


class TestScoreModel:
    def test_reasoning_task_boosts_reasoning_score(self):
        high_reason = _make_model("high", reasoning_score=9)
        low_reason = _make_model("low", reasoning_score=3)
        assert _score_model(high_reason, TaskType.PLANNING) > _score_model(
            low_reason, TaskType.PLANNING
        )

    def test_creative_task_boosts_creativity_score(self):
        high_creative = _make_model("high", creativity_score=9)
        low_creative = _make_model("low", creativity_score=3)
        assert _score_model(high_creative, TaskType.WRITING) > _score_model(
            low_creative, TaskType.WRITING
        )

    def test_latency_sensitive_boosts_latency_score(self):
        fast = _make_model("fast", latency_score=9)
        slow = _make_model("slow", latency_score=2)
        assert _score_model(fast, TaskType.EXTRACTION) > _score_model(slow, TaskType.EXTRACTION)

    def test_cheaper_model_gets_cost_bonus(self):
        cheap = _make_model("cheap", cost_tier=CostTier.LOW)
        expensive = _make_model("expensive", cost_tier=CostTier.HIGH)
        assert _score_model(cheap, TaskType.WRITING) > _score_model(expensive, TaskType.WRITING)


class TestGetFallbackChain:
    def test_returns_ordered_by_score(self):
        registry = _multi_model_registry()
        chain = get_fallback_chain(TaskType.PLANNING, registry)
        assert len(chain) >= 2
        assert chain[0] == "openai:gpt-4o"

    def test_primary_model_first(self):
        registry = _multi_model_registry()
        chain = get_fallback_chain(
            TaskType.PLANNING, registry, primary_model_id="deepseek:deepseek-chat"
        )
        assert chain[0] == "deepseek:deepseek-chat"

    def test_primary_model_not_duplicated(self):
        registry = _multi_model_registry()
        chain = get_fallback_chain(TaskType.PLANNING, registry, primary_model_id="openai:gpt-4o")
        assert chain.count("openai:gpt-4o") == 1

    def test_excludes_no_structured_output_for_extraction(self):
        registry = _multi_model_registry()
        chain = get_fallback_chain(TaskType.EXTRACTION, registry)
        assert "ollama:llama3" not in chain

    def test_empty_registry_returns_empty(self):
        chain = get_fallback_chain(TaskType.PLANNING, {})
        assert chain == []

    def test_unknown_primary_prepended(self):
        registry = _multi_model_registry()
        chain = get_fallback_chain(TaskType.PLANNING, registry, primary_model_id="unknown:model")
        assert chain[0] == "unknown:model"
