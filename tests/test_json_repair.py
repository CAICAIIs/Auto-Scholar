from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from pydantic import BaseModel

from backend.utils.llm_client import structured_completion


@pytest.fixture(autouse=True)
def _mock_llm_client():
    with patch("backend.utils.llm_client.get_client", return_value=MagicMock()):
        yield


class SimpleModel(BaseModel):
    name: str
    value: int


class TestJsonRepairFallback:
    @pytest.mark.asyncio
    async def test_valid_json_passes_without_repair(self):
        valid_json = '{"name": "test", "value": 42}'
        with patch("backend.utils.llm_client._call_llm", new=AsyncMock(return_value=valid_json)):
            result = await structured_completion(
                messages=[{"role": "user", "content": "test"}],
                response_model=SimpleModel,
            )
        assert result.name == "test"
        assert result.value == 42

    @pytest.mark.asyncio
    async def test_missing_comma_repaired(self):
        broken_json = '{"name": "test" "value": 42}'
        with patch("backend.utils.llm_client._call_llm", new=AsyncMock(return_value=broken_json)):
            result = await structured_completion(
                messages=[{"role": "user", "content": "test"}],
                response_model=SimpleModel,
            )
        assert result.name == "test"
        assert result.value == 42

    @pytest.mark.asyncio
    async def test_trailing_comma_repaired(self):
        broken_json = '{"name": "test", "value": 42,}'
        with patch("backend.utils.llm_client._call_llm", new=AsyncMock(return_value=broken_json)):
            result = await structured_completion(
                messages=[{"role": "user", "content": "test"}],
                response_model=SimpleModel,
            )
        assert result.name == "test"
        assert result.value == 42

    @pytest.mark.asyncio
    async def test_single_quotes_repaired(self):
        broken_json = "{'name': 'test', 'value': 42}"
        with patch("backend.utils.llm_client._call_llm", new=AsyncMock(return_value=broken_json)):
            result = await structured_completion(
                messages=[{"role": "user", "content": "test"}],
                response_model=SimpleModel,
            )
        assert result.name == "test"
        assert result.value == 42

    @pytest.mark.asyncio
    async def test_completely_invalid_json_raises(self):
        garbage = "this is not json at all"
        with patch("backend.utils.llm_client._call_llm", new=AsyncMock(return_value=garbage)):
            with pytest.raises(ValueError, match="LLM 返回无效 JSON"):
                await structured_completion(
                    messages=[{"role": "user", "content": "test"}],
                    response_model=SimpleModel,
                )

    @pytest.mark.asyncio
    async def test_repair_non_dict_raises(self):
        array_json = "[1, 2, 3"
        with patch("backend.utils.llm_client._call_llm", new=AsyncMock(return_value=array_json)):
            with pytest.raises(ValueError, match="LLM 返回无效 JSON"):
                await structured_completion(
                    messages=[{"role": "user", "content": "test"}],
                    response_model=SimpleModel,
                )


class NestedModel(BaseModel):
    title: str
    sections: list[str]


class TestJsonRepairNestedStructures:
    @pytest.mark.asyncio
    async def test_nested_missing_comma_repaired(self):
        broken_json = '{"title": "Review" "sections": ["intro", "methods"]}'
        with patch("backend.utils.llm_client._call_llm", new=AsyncMock(return_value=broken_json)):
            result = await structured_completion(
                messages=[{"role": "user", "content": "test"}],
                response_model=NestedModel,
            )
        assert result.title == "Review"
        assert result.sections == ["intro", "methods"]

    @pytest.mark.asyncio
    async def test_truncated_json_repaired(self):
        truncated = '{"title": "Review", "sections": ["intro", "methods"'
        with patch("backend.utils.llm_client._call_llm", new=AsyncMock(return_value=truncated)):
            result = await structured_completion(
                messages=[{"role": "user", "content": "test"}],
                response_model=NestedModel,
            )
        assert result.title == "Review"
        assert result.sections == ["intro", "methods"]
