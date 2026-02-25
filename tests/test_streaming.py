import asyncio
import json

import pytest

from backend.utils.llm_client import (
    TokenCallback,
    _call_llm_streaming,
    token_callback_var,
)


class TestTokenCallbackVar:
    def test_default_is_none(self):
        assert token_callback_var.get(None) is None

    def test_set_and_reset(self):
        async def dummy(token: str) -> None:
            pass

        reset = token_callback_var.set(dummy)
        assert token_callback_var.get(None) is dummy
        token_callback_var.reset(reset)
        assert token_callback_var.get(None) is None


class TestCallLlmStreaming:
    async def test_collects_all_tokens(self, monkeypatch):
        collected: list[str] = []

        async def on_token(token: str) -> None:
            collected.append(token)

        class FakeDelta:
            def __init__(self, content):
                self.content = content

        class FakeChoice:
            def __init__(self, content):
                self.delta = FakeDelta(content)

        class FakeUsage:
            def __init__(self, prompt, completion):
                self.prompt_tokens = prompt
                self.completion_tokens = completion

        class FakeChunk:
            def __init__(self, content=None, usage=None):
                self.choices = [FakeChoice(content)] if content else []
                self.usage = usage

        async def fake_create(**kwargs):
            assert kwargs.get("stream") is True
            chunks = [
                FakeChunk(content='{"con'),
                FakeChunk(content='tent":'),
                FakeChunk(content=' "hello"}'),
                FakeChunk(usage=FakeUsage(100, 50)),
            ]
            for c in chunks:
                yield c

        class FakeCompletions:
            async def create(self, **kwargs):
                return fake_create(**kwargs)

        class FakeChat:
            completions = FakeCompletions()

        class FakeClient:
            chat = FakeChat()

        from backend.evaluation.cost_tracker import reset_tracking

        reset_tracking()

        result = await _call_llm_streaming(
            client=FakeClient(),
            augmented_messages=[{"role": "user", "content": "test"}],
            temperature=0.3,
            max_tokens=100,
            on_token=on_token,
            model_name="gpt-4o",
            use_json_mode=True,
            task_type="writing",
        )

        assert result == '{"content": "hello"}'
        assert collected == ['{"con', 'tent":', ' "hello"}']

        reset_tracking()

    async def test_raises_on_empty_response(self, monkeypatch):
        async def on_token(token: str) -> None:
            pass

        async def fake_create(**kwargs):
            return
            yield  # noqa: E501 - make it an async generator

        class FakeCompletions:
            async def create(self, **kwargs):
                return fake_create(**kwargs)

        class FakeChat:
            completions = FakeCompletions()

        class FakeClient:
            chat = FakeChat()

        with pytest.raises(ValueError, match="empty response"):
            await _call_llm_streaming(
                client=FakeClient(),
                augmented_messages=[{"role": "user", "content": "test"}],
                temperature=0.3,
                max_tokens=100,
                on_token=on_token,
                model_name="gpt-4o",
            )


class TestStructuredCompletionWithStreaming:
    async def test_uses_streaming_when_callback_set(self, monkeypatch):
        collected: list[str] = []

        async def on_token(token: str) -> None:
            collected.append(token)

        class FakeDelta:
            def __init__(self, content):
                self.content = content

        class FakeChoice:
            def __init__(self, content):
                self.delta = FakeDelta(content)

        class FakeUsage:
            def __init__(self):
                self.prompt_tokens = 50
                self.completion_tokens = 30

        class FakeChunk:
            def __init__(self, content=None, usage=None):
                self.choices = [FakeChoice(content)] if content else []
                self.usage = usage

        async def fake_create(**kwargs):
            chunks = [
                FakeChunk(content='{"heading": "Test",'),
                FakeChunk(content=' "content": "Hello world"}'),
                FakeChunk(usage=FakeUsage()),
            ]
            for c in chunks:
                yield c

        class FakeCompletions:
            async def create(self, **kwargs):
                if kwargs.get("stream"):
                    return fake_create(**kwargs)
                raise AssertionError("Expected streaming call")

        class FakeChat:
            completions = FakeCompletions()

        class FakeClient:
            chat = FakeChat()

        from backend.schemas import ReviewSection
        from backend.utils.llm_client import structured_completion

        monkeypatch.setattr(
            "backend.utils.llm_client.resolve_model",
            lambda model_id: (FakeClient(), "gpt-4o", True),
        )

        from backend.evaluation.cost_tracker import reset_tracking

        reset_tracking()

        reset = token_callback_var.set(on_token)
        try:
            result = await structured_completion(
                messages=[
                    {"role": "system", "content": "Generate a section."},
                    {"role": "user", "content": "Write about AI."},
                ],
                response_model=ReviewSection,
                task_type="writing",
            )
            assert result.heading == "Test"
            assert result.content == "Hello world"
            assert len(collected) == 2
        finally:
            token_callback_var.reset(reset)
            reset_tracking()

    async def test_no_streaming_without_callback(self, monkeypatch):
        class FakeUsage:
            prompt_tokens = 10
            completion_tokens = 5

        class FakeMessage:
            content = '{"heading": "Test", "content": "No stream"}'

        class FakeChoice:
            message = FakeMessage()

        class FakeCompletion:
            usage = FakeUsage()
            choices = [FakeChoice()]

        class FakeCompletions:
            async def create(self, **kwargs):
                assert kwargs.get("stream") is not True
                return FakeCompletion()

        class FakeChat:
            completions = FakeCompletions()

        class FakeClient:
            chat = FakeChat()

        from backend.schemas import ReviewSection
        from backend.utils.llm_client import structured_completion

        monkeypatch.setattr(
            "backend.utils.llm_client.resolve_model",
            lambda model_id: (FakeClient(), "gpt-4o", True),
        )

        from backend.evaluation.cost_tracker import reset_tracking

        reset_tracking()

        assert token_callback_var.get(None) is None
        result = await structured_completion(
            messages=[
                {"role": "system", "content": "Generate a section."},
                {"role": "user", "content": "Write about AI."},
            ],
            response_model=ReviewSection,
            task_type="writing",
        )
        assert result.heading == "Test"
        assert result.content == "No stream"

        reset_tracking()
