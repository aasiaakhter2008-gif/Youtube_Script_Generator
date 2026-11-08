"""Shared LLM runtime concerns: semaphore, token-bucket rate limiter, cooldowns, response cache, events.

Kept in one module so every LLM call path (Gemini chain, Groq fallback, embeddings can opt in later)
shares the same budget and cooldown state. Nothing here ever logs API keys or prompt contents.
"""

import asyncio
import hashlib
import logging
import time
from contextvars import ContextVar
from typing import Any, Awaitable, Callable, Optional

from app.core.config import settings

logger = logging.getLogger("youtube_script_generator")

_CACHE_MAX = 128

LLMEventHook = Callable[[dict], Awaitable[None]]

_semaphore: Optional[asyncio.Semaphore] = None
_bucket: Optional["TokenBucket"] = None
_cooldowns: dict[str, float] = {}
_response_cache: dict[str, tuple[float, Any]] = {}
_model_usage: dict[str, dict[str, str]] = {}
_llm_event_hook: Optional[LLMEventHook] = None
_current_job_id: ContextVar[Optional[str]] = ContextVar("llm_current_job_id", default=None)


class TokenBucket:
    """Simple async token bucket: capacity = rate, refilled at rate/60 tokens per second."""

    def __init__(self, per_minute: int) -> None:
        self.capacity = max(1, int(per_minute))
        self.tokens = float(self.capacity)
        self.rate = self.capacity / 60.0
        self.last = time.monotonic()
        self._lock = asyncio.Lock()

    async def acquire(self) -> None:
        while True:
            async with self._lock:
                now = time.monotonic()
                self.tokens = min(self.capacity, self.tokens + (now - self.last) * self.rate)
                self.last = now
                if self.tokens >= 1.0:
                    self.tokens -= 1.0
                    return
                wait = (1.0 - self.tokens) / self.rate
            await asyncio.sleep(wait)


def get_semaphore() -> asyncio.Semaphore:
    global _semaphore
    if _semaphore is None:
        _semaphore = asyncio.Semaphore(max(1, int(settings.LLM_MAX_CONCURRENCY)))
    return _semaphore


def get_rate_limiter() -> TokenBucket:
    global _bucket
    target = max(1, int(settings.LLM_REQUESTS_PER_MINUTE))
    if _bucket is None or _bucket.capacity != target:
        _bucket = TokenBucket(target)
    return _bucket


def cooldown_remaining(model: str) -> float:
    return max(0.0, _cooldowns.get(model, 0.0) - time.monotonic())


def is_in_cooldown(model: str) -> bool:
    return cooldown_remaining(model) > 0.0


def set_cooldown(model: str, seconds: float) -> None:
    """Mark a model unreachable until its Retry-After (daily quotas can be ~12-24h), capped at 24h."""
    seconds = min(max(1.0, float(seconds)), 86400.0)
    _cooldowns[model] = time.monotonic() + seconds
    logger.warning("llm model entering cooldown", extra={"model": model, "seconds": round(seconds, 1)})


def cache_key(model: str, prompt: str, tool_name: Optional[str] = None) -> str:
    return hashlib.sha256(f"{model}|{tool_name or ''}|{prompt}".encode("utf-8")).hexdigest()


def cache_get(key: str, ttl: float) -> Optional[Any]:
    entry = _response_cache.get(key)
    if entry is None:
        return None
    stored_at, value = entry
    if (time.monotonic() - stored_at) > ttl:
        _response_cache.pop(key, None)
        return None
    return value


def cache_set(key: str, value: Any) -> None:
    if len(_response_cache) >= _CACHE_MAX:
        oldest = min(_response_cache.items(), key=lambda kv: kv[1][0])[0]
        _response_cache.pop(oldest, None)
    _response_cache[key] = (time.monotonic(), value)


def set_llm_event_hook(hook: Optional[LLMEventHook]) -> None:
    global _llm_event_hook
    _llm_event_hook = hook


def get_llm_event_hook() -> Optional[LLMEventHook]:
    return _llm_event_hook


async def emit_llm_event(event: dict) -> None:
    hook = _llm_event_hook
    if hook is None:
        return
    try:
        await hook(event)
    except Exception:  # pragma: no cover - never break the LLM path
        logger.debug("llm event hook failed", exc_info=True)


def record_model_use(role: str, model: str) -> None:
    """Remember which model actually served each pipeline role for the current job."""
    job_id = _current_job_id.get()
    if not job_id:
        return
    _model_usage.setdefault(job_id, {})[role] = model


def model_usage_for_job(job_id: str) -> dict[str, str]:
    return dict(_model_usage.get(job_id, {}))


def clear_model_usage(job_id: str) -> None:
    _model_usage.pop(job_id, None)


def set_current_job_id(job_id: Optional[str]) -> None:
    _current_job_id.set(job_id)


def reset_current_job_id() -> None:
    _current_job_id.set(None)


def current_job_id() -> Optional[str]:
    return _current_job_id.get()


def reset_llm_runtime() -> None:
    """Test hook: clear semaphore, bucket, cooldowns, cache and the event hook."""
    global _semaphore, _bucket
    _semaphore = None
    _bucket = None
    _cooldowns.clear()
    _response_cache.clear()
    _model_usage.clear()
    _llm_event_hook = None
    _current_job_id.set(None)
