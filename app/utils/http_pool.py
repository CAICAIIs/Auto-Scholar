"""HTTP connection pool for TCP connection reuse.

Why connection pooling matters:
- Original code created new aiohttp.ClientSession per function call
- Each new session = new TCP connection = TLS handshake overhead
- With pooling: connections are reused, reducing latency by ~50ms per request

Configuration rationale:
- limit=50: Semantic Scholar rate limit is 100 req/s, we use half for safety margin
- ttl_dns_cache=300: Cache DNS for 5 minutes, reduces DNS lookup overhead
"""
from aiohttp import ClientSession, ClientTimeout, TCPConnector

_session: ClientSession | None = None


async def get_session() -> ClientSession:
    """Get or create the shared HTTP session.
    
    Thread-safe for asyncio (single event loop).
    Session is lazily created on first call.
    """
    global _session
    if _session is None or _session.closed:
        connector = TCPConnector(limit=50, ttl_dns_cache=300)
        timeout = ClientTimeout(total=60)
        _session = ClientSession(connector=connector, timeout=timeout)
    return _session


async def close_session() -> None:
    """Close the shared HTTP session.
    
    Call this during application shutdown to release resources.
    """
    global _session
    if _session is not None and not _session.closed:
        await _session.close()
        _session = None
