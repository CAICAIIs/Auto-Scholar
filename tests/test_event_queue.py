import asyncio

import pytest

from backend.utils.event_queue import StreamingEventQueue


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
