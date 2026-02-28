import asyncio

import pytest

from backend.utils.event_queue import JsonFieldExtractor, StreamingEventQueue


@pytest.mark.asyncio
async def test_semantic_boundary_flush():
    """语义边界（标点）触发立即 flush"""
    queue = StreamingEventQueue()
    await queue.start()

    await queue.push("你")
    await queue.push("好")
    await queue.push("。")

    collected: list[str] = []

    async def collect():
        async for chunk in queue.consume():
            collected.append(chunk)

    consumer_task = asyncio.create_task(collect())
    await asyncio.sleep(0.05)
    await queue.close()
    await consumer_task

    assert "".join(collected) == "你好。"
    stats = queue.get_stats()
    assert stats["total_tokens"] == 3
    assert stats["total_flushes"] >= 1


@pytest.mark.asyncio
async def test_time_window_flush():
    """时间窗口（200ms）触发 flush"""
    queue = StreamingEventQueue()
    await queue.start()

    for char in "abcdef":
        await queue.push(char)
        await asyncio.sleep(0.01)

    await asyncio.sleep(0.25)
    await queue.close()

    collected: list[str] = []
    async for chunk in queue.consume():
        collected.append(chunk)

    assert "".join(collected) == "abcdef"
    stats = queue.get_stats()
    assert stats["total_tokens"] == 6
    assert stats["total_flushes"] <= 3


@pytest.mark.asyncio
async def test_compression_ratio():
    """验证压缩比：100 tokens 应该远少于 100 次 flush"""
    queue = StreamingEventQueue()
    await queue.start()

    for i in range(100):
        await queue.push(f"t{i}")
        await asyncio.sleep(0.005)

    await queue.close()

    collected: list[str] = []
    async for chunk in queue.consume():
        collected.append(chunk)

    stats = queue.get_stats()
    assert stats["total_tokens"] == 100
    assert stats["total_flushes"] < 20
    assert stats["compression_ratio"] >= 5


@pytest.mark.asyncio
async def test_mixed_boundaries():
    """混合场景：标点 + 时间窗口"""
    queue = StreamingEventQueue()
    await queue.start()

    await queue.push("Hello")
    await queue.push("!")
    await asyncio.sleep(0.01)
    await queue.push("World")
    await queue.push("\n")
    await queue.push("End")

    await queue.close()

    collected: list[str] = []
    async for chunk in queue.consume():
        collected.append(chunk)

    assert "".join(collected) == "Hello!World\nEnd"
    stats = queue.get_stats()
    assert stats["total_tokens"] == 5
    assert stats["total_flushes"] >= 2


@pytest.mark.asyncio
async def test_empty_queue():
    """空队列直接关闭"""
    queue = StreamingEventQueue()
    await queue.start()
    await queue.close()

    collected: list[str] = []
    async for chunk in queue.consume():
        collected.append(chunk)

    assert collected == []
    stats = queue.get_stats()
    assert stats["total_tokens"] == 0
    assert stats["total_flushes"] == 0


class TestJsonFieldExtractor:
    def test_extracts_content_from_complete_json(self):
        ext = JsonFieldExtractor("content")
        result = ext.feed('{"heading": "Intro", "content": "Hello world"}')
        assert result == "Hello world"

    def test_extracts_across_token_boundaries(self):
        ext = JsonFieldExtractor("content")
        parts = []
        for token in ['"con', 'tent"', ': "He', "llo w", 'orld"']:
            r = ext.feed(token)
            if r:
                parts.append(r)
        assert "".join(parts) == "Hello world"

    def test_ignores_other_fields(self):
        ext = JsonFieldExtractor("content")
        result = ext.feed('{"heading": "Title", "cited_paper_ids": ["a"]}')
        assert result is None

    def test_handles_escaped_characters(self):
        ext = JsonFieldExtractor("content")
        result = ext.feed('{"content": "line1\\nline2\\ttab\\"quote"}')
        assert result == 'line1\nline2\ttab"quote'

    def test_extracts_heading_field(self):
        ext = JsonFieldExtractor("heading")
        result = ext.feed('{"heading": "Introduction", "content": "text"}')
        assert result == "Introduction"

    def test_multiple_content_fields(self):
        ext = JsonFieldExtractor("content")
        parts = []
        r = ext.feed('{"heading": "A", "content": "first"}')
        if r:
            parts.append(r)
        r = ext.feed(', {"heading": "B", "content": "second"}')
        if r:
            parts.append(r)
        assert parts == ["first", "second"]

    def test_single_char_tokens(self):
        ext = JsonFieldExtractor("content")
        json_str = '{"content": "abc"}'
        parts = []
        for ch in json_str:
            r = ext.feed(ch)
            if r:
                parts.append(r)
        assert "".join(parts) == "abc"

    def test_returns_none_for_empty_content(self):
        ext = JsonFieldExtractor("content")
        result = ext.feed('{"content": ""}')
        assert result is None

    def test_no_false_match_on_partial_key(self):
        ext = JsonFieldExtractor("content")
        result = ext.feed('{"my_content": "should not match"}')
        assert result is None

    def test_buffer_until_complete_emits_full_value(self):
        ext = JsonFieldExtractor("heading", buffer_until_complete=True)
        parts = []
        for token in ['"heading"', ":", ' "', "引言", "与", "背景", '"']:
            r = ext.feed(token)
            if r:
                parts.append(r)
        assert parts == ["引言与背景"]

    def test_buffer_until_complete_multiple_values(self):
        ext = JsonFieldExtractor("heading", buffer_until_complete=True)
        parts = []
        tokens = [
            '{"heading"',
            ":",
            ' "',
            "A",
            "B",
            '"',
            ', "content": "x"}',
            ', {"heading"',
            ":",
            ' "',
            "C",
            "D",
            '"',
            "}",
        ]
        for token in tokens:
            r = ext.feed(token)
            if r:
                parts.append(r)
        assert parts == ["AB", "CD"]

    def test_streaming_content_not_buffered(self):
        ext = JsonFieldExtractor("content", buffer_until_complete=False)
        parts = []
        for token in ['"content"', ":", ' "', "Hello", " ", "World", '"']:
            r = ext.feed(token)
            if r:
                parts.append(r)
        assert parts == ["Hello", " ", "World"]
