from __future__ import annotations

import time
from collections import defaultdict, deque

from fastapi import HTTPException, Request, status

_WINDOW_SECONDS = 60
_buckets: dict[tuple[str, str], deque] = defaultdict(deque)


def rate_limit(bucket: str, limit: int):
    async def dependency(request: Request) -> None:
        client = request.client.host if request.client else "unknown"
        key = (client, bucket)
        now = time.monotonic()
        queue = _buckets[key]
        while queue and now - queue[0] > _WINDOW_SECONDS:
            queue.popleft()
        if len(queue) >= limit:
            raise HTTPException(status_code=status.HTTP_429_TOO_MANY_REQUESTS, detail="Rate limit exceeded")
        queue.append(now)

    return dependency
