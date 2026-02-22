import asyncio
import time
from collections.abc import AsyncIterator


class StreamingEventQueue:
    """
    防抖流式引擎：合并 LLM 离散 Token 输出，减少 90% SSE 网络请求。
    
    策略：
    1. 时间窗口：每 200ms flush 一次 buffer
    2. 语义边界：遇到标点符号（。！？\n）立即 flush
    """

    FLUSH_INTERVAL_MS: float = 200.0
    SEMANTIC_BOUNDARIES: frozenset[str] = frozenset({"。", "！", "？", ".", "!", "?", "\n"})

    def __init__(self) -> None:
        self._buffer: list[str] = []
        self._queue: asyncio.Queue[str | None] = asyncio.Queue()
        self._last_flush_time: float = time.monotonic()
        self._closed: bool = False
        self._flush_task: asyncio.Task[None] | None = None
        self._stats_total_tokens: int = 0
        self._stats_total_flushes: int = 0

    async def start(self) -> None:
        """启动后台定时 flush 任务"""
        if self._flush_task is None:
            self._flush_task = asyncio.create_task(self._periodic_flush())

    async def _periodic_flush(self) -> None:
        """后台定时器：每 200ms 检查并 flush"""
        while not self._closed:
            await asyncio.sleep(self.FLUSH_INTERVAL_MS / 1000.0)
            await self._try_flush(force=False)

    async def _try_flush(self, force: bool = False) -> None:
        """尝试 flush buffer 到队列"""
        if not self._buffer:
            return

        now = time.monotonic()
        elapsed_ms = (now - self._last_flush_time) * 1000.0

        if force or elapsed_ms >= self.FLUSH_INTERVAL_MS:
            merged = "".join(self._buffer)
            self._buffer.clear()
            self._last_flush_time = now
            self._stats_total_flushes += 1
            await self._queue.put(merged)

    def _should_flush_on_boundary(self, token: str) -> bool:
        """检查 token 是否包含语义边界"""
        return any(ch in self.SEMANTIC_BOUNDARIES for ch in token)

    async def push(self, token: str) -> None:
        """
        推送单个 token 到 buffer。
        遇到语义边界时立即 flush。
        """
        if self._closed:
            return

        self._buffer.append(token)
        self._stats_total_tokens += 1

        if self._should_flush_on_boundary(token):
            await self._try_flush(force=True)

    async def close(self) -> None:
        """关闭队列，flush 剩余内容，发送终止信号"""
        if self._closed:
            return

        self._closed = True

        if self._flush_task:
            self._flush_task.cancel()
            try:
                await self._flush_task
            except asyncio.CancelledError:
                pass
            self._flush_task = None

        if self._buffer:
            merged = "".join(self._buffer)
            self._buffer.clear()
            self._stats_total_flushes += 1
            await self._queue.put(merged)

        await self._queue.put(None)

    async def consume(self) -> AsyncIterator[str]:
        """消费合并后的 chunks，直到收到终止信号"""
        while True:
            chunk = await self._queue.get()
            if chunk is None:
                break
            yield chunk

    def get_stats(self) -> dict[str, int | float]:
        """返回统计信息：总 token 数、总 flush 次数、压缩比"""
        return {
            "total_tokens": self._stats_total_tokens,
            "total_flushes": self._stats_total_flushes,
            "compression_ratio": (
                round(self._stats_total_tokens / self._stats_total_flushes, 2)
                if self._stats_total_flushes > 0
                else 0.0
            ),
        }
