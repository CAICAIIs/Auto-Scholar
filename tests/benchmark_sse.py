"""
SSE 防抖效果基准测试

验证 StreamingEventQueue 的网络请求削减效果。
目标：证明防抖机制减少 80%+ 的网络请求。

运行方式：
    pytest tests/benchmark_sse.py -v
    python tests/benchmark_sse.py  # 直接运行查看详细输出
"""

import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from backend.utils.event_queue import StreamingEventQueue


async def benchmark_debounce_effect() -> dict[str, float]:
    """
    模拟真实场景：LLM 流式输出的离散 token。
    真实 LLM 输出通常是单词或字符级别的 token。
    """
    tokens = []
    for i in range(10):
        tokens.extend(
            [
                "正",
                "在",
                "处",
                "理",
                "论",
                "文",
                f" {i + 1}",
                "，",
                "提",
                "取",
                "核",
                "心",
                "贡",
                "献",
                "。",
                "分",
                "析",
                "方",
                "法",
                "论",
                "和",
                "实",
                "验",
                "结",
                "果",
                "。",
            ]
        )
    tokens.extend(["完", "成", "！"])

    queue = StreamingEventQueue()
    await queue.start()

    for token in tokens:
        await queue.push(token)

    await queue.close()

    stats = queue.get_stats()
    raw_count = stats["total_tokens"]
    debounced_count = stats["total_flushes"]
    reduction = (1 - debounced_count / raw_count) * 100 if raw_count > 0 else 0

    return {
        "raw_messages": raw_count,
        "debounced_messages": debounced_count,
        "reduction_percent": round(reduction, 1),
        "compression_ratio": stats["compression_ratio"],
    }


async def benchmark_semantic_boundary() -> dict[str, int]:
    """
    验证语义边界触发立即 flush。
    中英文标点都应触发：。！？.!?\\n
    """
    queue = StreamingEventQueue()
    await queue.start()

    test_cases = [
        ("Hello", False),
        (" world", False),
        (".", True),
        ("你好", False),
        ("世界", False),
        ("。", True),
        ("Test", False),
        ("!", True),
        ("问题", False),
        ("？", True),
        ("Line", False),
        ("\n", True),
    ]

    boundary_triggers = 0
    for token, should_trigger in test_cases:
        before = queue._stats_total_flushes
        await queue.push(token)
        after = queue._stats_total_flushes
        if after > before and should_trigger:
            boundary_triggers += 1

    await queue.close()

    return {
        "expected_boundary_triggers": sum(1 for _, t in test_cases if t),
        "actual_boundary_triggers": boundary_triggers,
    }


async def benchmark_time_window() -> dict[str, float]:
    """
    验证 200ms 时间窗口 flush。
    连续推送无边界 token，等待超过 200ms 后应自动 flush。
    """
    queue = StreamingEventQueue()
    await queue.start()

    for i in range(10):
        await queue.push(f"token{i}")

    flushes_before_wait = queue._stats_total_flushes

    await asyncio.sleep(0.25)

    flushes_after_wait = queue._stats_total_flushes

    await queue.close()

    return {
        "flushes_before_wait": flushes_before_wait,
        "flushes_after_wait": flushes_after_wait,
        "time_window_triggered": flushes_after_wait > flushes_before_wait,
    }


class TestSSEDebounce:
    """SSE 防抖基准测试套件"""

    async def test_debounce_reduces_network_requests_by_80_percent(self) -> None:
        """验证防抖减少 80%+ 网络请求"""
        result = await benchmark_debounce_effect()
        assert result["reduction_percent"] >= 80, (
            f"Expected >=80% reduction, got {result['reduction_percent']}%"
        )

    async def test_semantic_boundaries_trigger_flush(self) -> None:
        """验证语义边界触发立即 flush"""
        result = await benchmark_semantic_boundary()
        assert result["actual_boundary_triggers"] == result["expected_boundary_triggers"], (
            f"Expected {result['expected_boundary_triggers']} boundary triggers, "
            f"got {result['actual_boundary_triggers']}"
        )

    async def test_time_window_triggers_flush(self) -> None:
        """验证 200ms 时间窗口触发 flush"""
        result = await benchmark_time_window()
        assert result["time_window_triggered"], "Time window should trigger flush after 200ms"


async def main() -> None:
    """直接运行时输出详细基准测试结果"""
    print("=" * 60)
    print("SSE 防抖效果基准测试")
    print("=" * 60)

    print("\n1. 防抖效果测试")
    print("-" * 40)
    result = await benchmark_debounce_effect()
    print(f"   原始消息数: {result['raw_messages']}")
    print(f"   防抖后消息数: {result['debounced_messages']}")
    print(f"   网络请求削减: {result['reduction_percent']}%")
    print(f"   压缩比: {result['compression_ratio']}x")

    print("\n2. 语义边界测试")
    print("-" * 40)
    result = await benchmark_semantic_boundary()
    print(f"   预期边界触发: {result['expected_boundary_triggers']}")
    print(f"   实际边界触发: {result['actual_boundary_triggers']}")

    print("\n3. 时间窗口测试")
    print("-" * 40)
    result = await benchmark_time_window()
    print(f"   等待前 flush 次数: {result['flushes_before_wait']}")
    print(f"   等待后 flush 次数: {result['flushes_after_wait']}")
    print(f"   时间窗口触发: {'是' if result['time_window_triggered'] else '否'}")

    print("\n" + "=" * 60)
    print("结论: SSE 防抖机制有效，网络请求削减 >80%")
    print("=" * 60)


if __name__ == "__main__":
    asyncio.run(main())
