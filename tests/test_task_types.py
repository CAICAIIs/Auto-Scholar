from backend.llm.task_types import (
    TASK_REQUIREMENTS,
    TaskRequirement,
    TaskType,
    get_task_requirement,
)


class TestTaskType:
    def test_all_task_types_have_requirements(self):
        for task_type in TaskType:
            assert task_type in TASK_REQUIREMENTS

    def test_task_type_values(self):
        assert TaskType.PLANNING == "planning"
        assert TaskType.EXTRACTION == "extraction"
        assert TaskType.WRITING == "writing"
        assert TaskType.QA == "qa"
        assert TaskType.REFLECTION == "reflection"

    def test_task_type_count(self):
        assert len(TaskType) == 5


class TestTaskRequirement:
    def test_default_values(self):
        req = TaskRequirement()
        assert req.needs_reasoning is False
        assert req.needs_structured_output is False
        assert req.needs_long_context is False
        assert req.prefers_creativity is False
        assert req.max_cost_tier == "high"
        assert req.latency_sensitive is False

    def test_frozen(self):
        req = TaskRequirement()
        try:
            req.needs_reasoning = True  # type: ignore[misc]
            assert False, "Should raise FrozenInstanceError"
        except AttributeError:
            pass

    def test_planning_requires_reasoning(self):
        req = get_task_requirement(TaskType.PLANNING)
        assert req.needs_reasoning is True
        assert req.needs_structured_output is True
        assert req.max_cost_tier == "high"

    def test_extraction_is_latency_sensitive(self):
        req = get_task_requirement(TaskType.EXTRACTION)
        assert req.needs_structured_output is True
        assert req.latency_sensitive is True
        assert req.max_cost_tier == "medium"

    def test_writing_prefers_creativity(self):
        req = get_task_requirement(TaskType.WRITING)
        assert req.prefers_creativity is True
        assert req.needs_long_context is True
        assert req.max_cost_tier == "high"

    def test_qa_is_cheap_and_fast(self):
        req = get_task_requirement(TaskType.QA)
        assert req.max_cost_tier == "low"
        assert req.latency_sensitive is True
        assert req.needs_structured_output is True

    def test_reflection_needs_reasoning(self):
        req = get_task_requirement(TaskType.REFLECTION)
        assert req.needs_reasoning is True
        assert req.needs_structured_output is True
        assert req.max_cost_tier == "medium"
