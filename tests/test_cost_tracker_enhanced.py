from backend.evaluation.cost_tracker import (
    estimate_cost_usd,
    get_cost_efficiency_from_tracking,
    get_total_cost_usd,
    record_llm_usage,
    reset_tracking,
)
from backend.evaluation.schemas import TaskCostBreakdown


class TestEstimateCostUsd:
    def test_known_model_gpt4o(self):
        cost = estimate_cost_usd(1_000_000, 1_000_000, "gpt-4o")
        assert cost == 2.50 + 10.00

    def test_known_model_deepseek_chat(self):
        cost = estimate_cost_usd(1_000_000, 1_000_000, "deepseek-chat")
        assert abs(cost - 0.42) < 1e-6

    def test_partial_match(self):
        cost = estimate_cost_usd(1_000_000, 0, "ft:gpt-4o-mini:custom")
        assert cost == 0.15

    def test_unknown_model_uses_default(self):
        cost = estimate_cost_usd(1_000_000, 1_000_000, "some-unknown-model")
        assert cost == 2.50 + 10.00

    def test_zero_tokens(self):
        cost = estimate_cost_usd(0, 0, "gpt-4o")
        assert cost == 0.0

    def test_small_token_count(self):
        cost = estimate_cost_usd(1000, 500, "gpt-4o")
        expected = (1000 / 1_000_000) * 2.50 + (500 / 1_000_000) * 10.00
        assert abs(cost - expected) < 1e-9

    def test_case_insensitive(self):
        cost = estimate_cost_usd(1_000_000, 0, "GPT-4O")
        assert cost == 2.50


class TestRecordLlmUsageWithTaskType:
    def setup_method(self):
        reset_tracking()

    def teardown_method(self):
        reset_tracking()

    def test_record_returns_cost(self):
        record = record_llm_usage(1000, 500, model="gpt-4o", task_type="writing")
        assert "cost_usd" in record
        assert record["cost_usd"] > 0
        assert record["task_type"] == "writing"

    def test_backward_compatible_no_task_type(self):
        record = record_llm_usage(1000, 500, model="gpt-4o")
        assert record["task_type"] == ""
        assert record["cost_usd"] > 0


class TestGetTotalCostUsd:
    def setup_method(self):
        reset_tracking()

    def teardown_method(self):
        reset_tracking()

    def test_empty(self):
        assert get_total_cost_usd() == 0.0

    def test_accumulates(self):
        record_llm_usage(1_000_000, 0, model="gpt-4o")
        record_llm_usage(1_000_000, 0, model="gpt-4o")
        assert get_total_cost_usd() == 5.0


class TestTaskBreakdown:
    def setup_method(self):
        reset_tracking()

    def teardown_method(self):
        reset_tracking()

    def test_per_task_type_breakdown(self):
        record_llm_usage(1000, 500, model="gpt-4o", task_type="planning")
        record_llm_usage(2000, 1000, model="gpt-4o", task_type="writing")
        record_llm_usage(500, 200, model="gpt-4o", task_type="planning")

        result = get_cost_efficiency_from_tracking()
        assert len(result.task_breakdown) == 2

        planning = next(b for b in result.task_breakdown if b.task_type == "planning")
        assert planning.prompt_tokens == 1500
        assert planning.completion_tokens == 700
        assert planning.llm_calls == 2

        writing = next(b for b in result.task_breakdown if b.task_type == "writing")
        assert writing.prompt_tokens == 2000
        assert writing.completion_tokens == 1000
        assert writing.llm_calls == 1

    def test_unknown_task_type_grouped(self):
        record_llm_usage(1000, 500, model="gpt-4o")
        record_llm_usage(2000, 1000, model="gpt-4o")

        result = get_cost_efficiency_from_tracking()
        assert len(result.task_breakdown) == 1
        assert result.task_breakdown[0].task_type == "unknown"
        assert result.task_breakdown[0].llm_calls == 2

    def test_total_cost_usd_in_result(self):
        record_llm_usage(1_000_000, 1_000_000, model="gpt-4o", task_type="writing")
        result = get_cost_efficiency_from_tracking()
        assert result.total_cost_usd == 12.5

    def test_empty_tracking(self):
        result = get_cost_efficiency_from_tracking()
        assert result.total_cost_usd == 0.0
        assert result.task_breakdown == []


class TestTaskCostBreakdownSchema:
    def test_total_tokens_computed(self):
        b = TaskCostBreakdown(task_type="qa", prompt_tokens=100, completion_tokens=50, llm_calls=1)
        assert b.total_tokens == 150

    def test_defaults(self):
        b = TaskCostBreakdown(task_type="test")
        assert b.prompt_tokens == 0
        assert b.completion_tokens == 0
        assert b.llm_calls == 0
        assert b.cost_usd == 0.0
