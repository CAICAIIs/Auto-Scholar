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

    HEARTBEAT_INTERVAL_S: float = 15.0
    HEARTBEAT_SENTINEL: str = "__heartbeat__"

    async def consume(self) -> AsyncIterator[str]:
        while True:
            try:
                chunk = await asyncio.wait_for(self._queue.get(), timeout=self.HEARTBEAT_INTERVAL_S)
                if chunk is None:
                    break
                yield chunk
            except TimeoutError:
                yield self.HEARTBEAT_SENTINEL

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


class JsonFieldExtractor:
    """
    从流式 JSON token 序列中提取指定字段的字符串值。

    状态机：SCANNING → SAW_KEY → SAW_COLON → IN_STRING
    用于从 structured_completion 的 JSON 流中提取 "content" / "heading" 等字段，
    过滤掉 JSON 结构符号（{, }, 字段名等），只保留用户可读文本。
    """

    _SCANNING = 0
    _SAW_KEY = 1
    _SAW_COLON = 2
    _IN_STRING = 3

    def __init__(self, field_name: str, buffer_until_complete: bool = False) -> None:
        self._key_pattern = f'"{field_name}"'
        self._key_len = len(self._key_pattern)
        self._state = self._SCANNING
        self._escape_next = False
        self._scan_buf = ""
        self._buffer_until_complete = buffer_until_complete
        self._value_buf: list[str] = []

    def feed(self, token: str) -> str | None:
        self._scan_buf += token
        parts: list[str] = []
        i = 0

        while i < len(self._scan_buf):
            ch = self._scan_buf[i]

            if self._state == self._SCANNING:
                pos = self._scan_buf.find(self._key_pattern, i)
                if pos == -1:
                    self._scan_buf = self._scan_buf[-(self._key_len - 1) :]
                    return self._emit(parts)
                i = pos + self._key_len
                self._state = self._SAW_KEY

            elif self._state == self._SAW_KEY:
                if ch == ":":
                    self._state = self._SAW_COLON
                elif not ch.isspace():
                    self._state = self._SCANNING
                i += 1

            elif self._state == self._SAW_COLON:
                if ch == '"':
                    self._state = self._IN_STRING
                elif not ch.isspace():
                    self._state = self._SCANNING
                i += 1

            elif self._state == self._IN_STRING:
                if self._escape_next:
                    self._escape_next = False
                    if ch == "n":
                        parts.append("\n")
                    elif ch == "t":
                        parts.append("\t")
                    elif ch in ('"', "\\", "/"):
                        parts.append(ch)
                    else:
                        parts.append(ch)
                elif ch == "\\":
                    self._escape_next = True
                elif ch == '"':
                    self._state = self._SCANNING
                    if self._buffer_until_complete:
                        self._value_buf.extend(parts)
                        parts = []
                        complete = "".join(self._value_buf)
                        self._value_buf.clear()
                        if complete:
                            parts.append(complete)
                else:
                    parts.append(ch)
                i += 1

        self._scan_buf = ""

        if self._buffer_until_complete and self._state == self._IN_STRING:
            self._value_buf.extend(parts)
            return None

        return self._emit(parts)

    @staticmethod
    def _emit(parts: list[str]) -> str | None:
        return "".join(parts) if parts else None
