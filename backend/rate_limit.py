from __future__ import annotations

import os
import threading
import time
from collections import defaultdict, deque

from fastapi import HTTPException

_LOCK = threading.Lock()
_BUCKETS: dict[tuple[str, str], deque[float]] = defaultdict(deque)


def get_rate_limit_per_minute() -> int:
    try:
        return max(1, int(os.getenv("RATE_LIMIT_PER_MINUTE", "30")))
    except ValueError:
        return 30


def enforce_rate_limit(
    uid: str,
    bucket: str,
    limit: int | None = None,
    window_seconds: float = 60.0,
) -> None:
    """Thread-safe per-tenant sliding-window rate limiter for costly inference endpoints."""
    max_requests = limit if limit is not None else get_rate_limit_per_minute()
    now = time.monotonic()
    cutoff = now - window_seconds
    key = (uid or "anonymous", bucket)

    with _LOCK:
        q = _BUCKETS[key]
        while q and q[0] <= cutoff:
            q.popleft()
        if len(q) >= max_requests:
            retry_after = max(1, int(window_seconds - (now - q[0])))
            raise HTTPException(
                status_code=429,
                detail=f"Rate limit exceeded ({max_requests} requests/{int(window_seconds)}s). Try again in {retry_after}s.",
                headers={"Retry-After": str(retry_after)},
            )
        q.append(now)
