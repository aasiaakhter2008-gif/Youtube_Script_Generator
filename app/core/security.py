import threading
import time
from collections import defaultdict, deque
from typing import Optional

from fastapi import Header, HTTPException, Request

from app.core.config import settings
from app.services.api_keys import api_key_store

_lock = threading.Lock()
_buckets: dict[str, deque] = defaultdict(deque)


def _rate_limit_allows(bucket_key: str, limit: Optional[int] = None) -> bool:
    now = time.monotonic()
    window = max(1, settings.RATE_LIMIT_WINDOW_SECONDS)
    max_per_window = max(1, limit if limit is not None else settings.RATE_LIMIT_PER_MINUTE)
    with _lock:
        timestamps = _buckets[bucket_key]
        while timestamps and (now - timestamps[0]) > window:
            timestamps.popleft()
        if len(timestamps) >= max_per_window:
            return False
        timestamps.append(now)
        return True


def _client_ip(request: Optional[Request]) -> str:
    if request is None:
        return "unknown"
    forwarded = request.headers.get("x-forwarded-for")
    if forwarded:
        return forwarded.split(",")[0].strip() or "unknown"
    if request.client is not None:
        return request.client.host or "unknown"
    return "unknown"


async def verify_api_key(
    request: Request,
    x_api_key: Optional[str] = Header(default=None, alias="X-API-Key"),
) -> str:
    """API key auth via X-API-Key header + per-key rate limiting + per-IP bucket. Scoped keys supported."""
    key = (x_api_key or "").strip()
    ip = _client_ip(request)
    # Loose IP ceiling: ~4x per-key limit so a burst of unauthenticated requests hits the wall first.
    ip_limit = max(60, settings.RATE_LIMIT_PER_MINUTE * 6)
    if not _rate_limit_allows(f"ip:{ip}", limit=ip_limit):
        raise HTTPException(status_code=429, detail="Too many requests from this address. Try again later.")
    if not key:
        raise HTTPException(status_code=401, detail="Invalid or missing API key")
    api_key = api_key_store.get_by_key(key)
    if api_key is not None and api_key.revoked:
        raise HTTPException(status_code=401, detail="API key revoked")
    if api_key is None and key != settings.API_KEY:
        raise HTTPException(status_code=401, detail="Invalid or missing API key")
    rate_key = api_key.key_id if api_key is not None else f"global-default:{ip}"
    limit = api_key.rate_limit_per_minute if api_key is not None else settings.RATE_LIMIT_PER_MINUTE
    if not _rate_limit_allows(rate_key, limit=limit):
        raise HTTPException(status_code=429, detail="Rate limit exceeded. Try again later.")
    return api_key.owner if api_key is not None else "global"
