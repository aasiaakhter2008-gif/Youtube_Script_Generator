import json
import logging
import random
import re
from abc import ABC, abstractmethod
from typing import Any, Optional, TypeVar

import httpx
from anthropic import AsyncAnthropic
from openai import APIStatusError, APITimeoutError, AsyncOpenAI
from pydantic import BaseModel, ValidationError
from tenacity import (
    retry,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
    wait_random,
)

from app.core.config import settings
from app.services import llm_runtime

logger = logging.getLogger("youtube_script_generator")

T = TypeVar("T", bound=BaseModel)

_RETRYABLE_STATUS = (429, 503)


class BaseLLMClient(ABC):
    """Provider-agnostic structured LLM client (Anthropic Claude or Google Gemini / Groq today)."""

    @abstractmethod
    async def structured(self, prompt: str, schema: type[T], **kwargs: Any) -> T:
        raise NotImplementedError


class _RetryableLLMError(RuntimeError):
    """429 / 503 / invalid LLM JSON output. Retried with backoff+jitter, then fallback decides next model."""


class _ModelTimeoutError(RuntimeError):
    """A single model exceeded the request timeout. Not retried on the same model:
    fallback moves on and the model is put in cooldown so later sections skip it."""


def _retry_after_seconds(exc: Exception) -> Optional[float]:
    """Extract a Retry-After hint (header or Google RPCs RetryInfo body), seconds."""
    response = getattr(exc, "response", None)
    if response is not None:
        headers = getattr(response, "headers", None) or {}
        for name in ("retry-after", "Retry-After"):
            value = headers.get(name)
            try:
                if value is not None:
                    return float(value)
            except (TypeError, ValueError):
                pass
    body = getattr(exc, "body", None) or getattr(exc, "message", None) or str(exc)
    match = re.search(r"retryDelay[\"']?\s*:\s*[\"']?([0-9]+(?:\.[0-9]+)?)", str(body))
    if match:
        try:
            return float(match.group(1))
        except ValueError:
            return None
    return None


def _wait_for_retry(retry_state) -> float:
    """Exponential backoff + jitter; honors an upstream Retry-After when present."""
    exc = retry_state.outcome.exception() if retry_state.outcome is not None else None
    retry_after = _retry_after_seconds(exc) if exc is not None else None
    if retry_after is not None:
        # Base (in-client) retries stay short; full Retry-After is honored via the cooldown marker between models.
        return min(max(float(retry_after), 0.2), 2.0) + random.uniform(0, 0.5)
    backoff = wait_exponential(multiplier=1, min=1, max=10)
    jitter = wait_random(0, 2)
    return backoff(retry_state) + jitter(retry_state)


def _short_error(exc: Exception) -> str:
    return re.sub(r"\s+", " ", str(exc) or exc.__class__.__name__).strip()[:180]


def _strip_json_fences(text: str) -> str:
    """Strip markdown code fences (```json ... ```) from an LLM response before JSON parsing."""
    cleaned = text.strip()
    if cleaned.startswith("```"):
        parts = cleaned.split("```")
        cleaned = parts[1].strip() if len(parts) > 1 else cleaned
        if cleaned.lower().startswith("json"):
            cleaned = cleaned[4:].strip()
    return cleaned


class AnthropicLLMClient(BaseLLMClient):
    """Anthropic Claude via official SDK: tool-use forced structured output + tenacity retries."""

    def __init__(
        self,
        api_key: str,
        model: str,
        base_url: str = "https://api.anthropic.com",
        temperature: float = 0.7,
        max_retries: int = 3,
        backoff_base: float = 0.5,
        max_tokens: int = 4096,
    ) -> None:
        self.client: AsyncAnthropic = AsyncAnthropic(api_key=api_key or "sk-no-key-set",base_url=base_url,)
        self.model = model
        self.temperature = temperature
        self.max_retries = max_retries
        self.backoff_base = backoff_base
        self.max_tokens = max_tokens

    def _tool(self, schema: type, name: str, description: str) -> dict:
        json_schema = schema.model_json_schema()
        return {
            "name": name,
            "description": description,
            "input_schema": {
                "type": "object",
                "properties": json_schema.get("properties") or {},
                "required": json_schema.get("required") or [],
            },
        }

    async def _structured_call(self, prompt: str, tool: dict, schema: type) -> Any:
        @retry(
            stop=stop_after_attempt(self.max_retries),
            wait=wait_exponential(multiplier=self.backoff_base, min=1, max=8),
            reraise=True,
        )
        async def _do() -> Any:
            response = await self.client.messages.create(
                model=self.model,
                max_tokens=self.max_tokens,
                tools=[tool],
                tool_choice={"type": "tool", "name": tool["name"]},
                messages=[{"role": "user", "content": prompt}],
            )
            tool_use = None
            for block in response.content:
                if getattr(block, "type", None) == "tool_use":
                    tool_use = block
                    break
            if tool_use is None:
                raise ValueError("LLM did not return a tool_use block")
            return tool_use.input

        return await _do()

    async def structured(self, prompt: str, schema: type[T], **kwargs: Any) -> T:
        tool_name = str(kwargs.get("tool_name") or f"{schema.__name__.lower()}_output")
        tool = self._tool(schema, tool_name, f"Structured output for {schema.__name__}")
        result = await self._structured_call(prompt, tool, schema)
        return schema.model_validate(result)


class GeminiLLMClient(BaseLLMClient):
    """Google Gemini via OpenAI-compatible endpoint (JSON response format) + tenacity retries with jitter."""

    _provider_label = "Gemini"

    def __init__(
        self,
        api_key: str,
        model: str,
        base_url: str = "https://generativelanguage.googleapis.com/v1beta/openai/",
        temperature: float = 0.7,
        max_retries: int = 3,
        backoff_base: float = 0.5,
        max_tokens: int = 4096,
        timeout: float = 120.0,
    ) -> None:
        self.client: AsyncOpenAI = AsyncOpenAI(
            api_key=api_key or f"{self._provider_label.lower()}-no-key-set",
            base_url=base_url,
            timeout=httpx.Timeout(timeout),
            # Retries are handled by tenacity + the fallback chain. The SDK's built-in
            # retry sleeps for the full Retry-After (often minutes on free-tier 503s),
            # which used to blow past the agent timeout before trying a fallback model.
            max_retries=0,
        )
        self.model = model
        self.temperature = temperature
        self.max_retries = max_retries
        self.backoff_base = backoff_base
        self.max_tokens = max_tokens

    async def _structured_call(self, prompt: str, tool: dict, schema: type) -> Any:
        @retry(
            retry=retry_if_exception_type(_RetryableLLMError),
            stop=stop_after_attempt(self.max_retries),
            wait=_wait_for_retry,
            reraise=True,
        )
        async def _do() -> Any:
            try:
                completion = await self.client.chat.completions.create(
                    model=self.model,
                    messages=[{"role": "user", "content": prompt}],
                    response_format={"type": "json_object"},
                    temperature=self.temperature,
                    max_tokens=self.max_tokens,
                )
            except (httpx.TimeoutException, APITimeoutError) as exc:
                raise _ModelTimeoutError(f"{self._provider_label} request timed out for model {self.model}: {exc}") from exc
            except APIStatusError as exc:
                status = getattr(exc, "status_code", None)
                detail = (getattr(exc, "message", "") or str(exc))[:300]
                if status == 429:
                    retry_after = _retry_after_seconds(exc)
                    raise _RetryableLLMError(
                        f"{self._provider_label} rate limit exceeded for model {self.model} (status 429, retry after {retry_after}s): {detail}"
                    ) from exc
                if status == 503:
                    retry_after = _retry_after_seconds(exc)
                    raise _RetryableLLMError(
                        f"{self._provider_label} service unavailable for model {self.model} (status 503, retry after {retry_after}s): {detail}"
                    ) from exc
                raise
            content = completion.choices[0].message.content
            if not content:
                raise _RetryableLLMError(f"{self._provider_label} returned an empty response for model {self.model}")
            try:
                return json.loads(_strip_json_fences(content))
            except json.JSONDecodeError as exc:
                raise _RetryableLLMError(f"{self._provider_label} returned invalid JSON for model {self.model}: {exc}") from exc

        return await _do()

    def _tool(self, schema: type, name: str, description: str) -> dict:
        json_schema = schema.model_json_schema()
        return {
            "name": name,
            "description": description,
            "json_schema": {
                "type": "object",
                "properties": json_schema.get("properties") or {},
                "required": json_schema.get("required") or [],
            },
        }

    async def structured(self, prompt: str, schema: type[T], **kwargs: Any) -> T:
        tool_name = str(kwargs.get("tool_name") or f"{schema.__name__.lower()}_output")
        tool = self._tool(schema, tool_name, f"Structured output for {schema.__name__}")
        result = await self._structured_call(prompt, tool, schema)
        try:
            return schema.model_validate(result)
        except ValidationError as exc:
            # Shape-invalid output is usually a weak/echoing model; give it another chance before the fallback chain decides.
            raise _RetryableLLMError(f"{self._provider_label} returned schema-invalid output for model {self.model}: {exc}") from exc


class GroqLLMClient(GeminiLLMClient):
    """Groq via OpenAI-compatible endpoint (JSON mode). Used as the last-resort fallback provider."""

    _provider_label = "Groq"

    def __init__(
        self,
        api_key: str,
        model: str,
        temperature: float = 0.7,
        max_retries: int = 3,
        backoff_base: float = 0.5,
        max_tokens: int = 4096,
        timeout: float = 120.0,
    ) -> None:
        super().__init__(
            api_key=api_key,
            model=model,
            base_url="https://api.groq.com/openai/v1/",
            temperature=temperature,
            max_retries=max_retries,
            backoff_base=backoff_base,
            max_tokens=max_tokens,
            timeout=timeout,
        )


class FallbackLLMClient(BaseLLMClient):
    """Ordered client chain: Gemini chain first, then optional Groq. Cache + global rate limit + per-model cooldowns.

    Agents' logic does not change: they call client.structured() and either get a validated result
    or a single RuntimeError listing every attempted model ("All LLM providers busy ... try again in ~1 minute").
    """

    def __init__(self, clients: list[BaseLLMClient], role: str = "writer") -> None:
        if not clients:
            raise ValueError("FallbackLLMClient requires at least one client")
        self.clients = list(clients)
        self.role = role

    @property
    def model(self) -> str:
        return getattr(self.clients[0], "model", "unknown")

    async def _emit(self, model: str, message: str) -> None:
        await llm_runtime.emit_llm_event(
            {
                "event": "llm.retry",
                "job_id": llm_runtime.current_job_id(),
                "model": model,
                "message": message,
            }
        )

    async def structured(self, prompt: str, schema: type[T], **kwargs: Any) -> T:
        tool_name = str(kwargs.get("tool_name") or "")
        attempts: list[str] = []

        for index, client in enumerate(self.clients):
            model = getattr(client, "model", f"client-{index}")
            cache_key = llm_runtime.cache_key(model, prompt, tool_name)
            cached = llm_runtime.cache_get(cache_key, ttl=settings.LLM_CACHE_TTL_SECONDS)
            if cached is not None:
                logger.info("llm cache hit", extra={"model": model})
                llm_runtime.record_model_use(self.role, f"{model} (cache)")
                await self._emit(model, f"Cache hit for {model}; serving cached result")
                return cached

            remaining = llm_runtime.cooldown_remaining(model)
            if remaining > 0:
                attempts.append(f"{model}: in cooldown ({remaining:.0f}s remaining)")
                await self._emit(model, f"{model} cooling down ({remaining:.0f}s) — trying fallback model")
                continue

            try:
                async with llm_runtime.get_semaphore():
                    await llm_runtime.get_rate_limiter().acquire()
                    result = await client.structured(prompt, schema, **kwargs)
                llm_runtime.cache_set(cache_key, result)
                llm_runtime.record_model_use(self.role, model)
                logger.info("llm request succeeded", extra={"model": model, "role": self.role})
                return result
            except Exception as exc:
                message = _short_error(exc)
                retry_after = _retry_after_seconds(exc)
                if isinstance(exc, _ModelTimeoutError):
                    # Slow/unresponsive model: skip it for a while so later sections of the
                    # same job do not each pay the timeout again.
                    cooldown = 300.0
                elif retry_after is not None:
                    cooldown = retry_after
                elif _is_rate_or_overload(exc):
                    cooldown = 30.0
                else:
                    cooldown = 0.0
                if cooldown > 0:
                    llm_runtime.set_cooldown(model, cooldown)
                attempts.append(f"{model}: {message}")
                next_model = self._next_candidate(index)
                await self._emit(
                    model,
                    f"Model busy: {model} ({message}) — trying fallback model{f' {next_model}' if next_model else ''}",
                )
                continue

        details = "; ".join(attempts) if attempts else "no clients registered"
        raise RuntimeError(
            f"All LLM providers busy ({details}). Gemini overloaded — retried every configured model; please try again in ~1 minute."
        )

    def _next_candidate(self, current_index: int) -> Optional[str]:
        for client in self.clients[current_index + 1 :]:
            model = getattr(client, "model", None)
            if model and not llm_runtime.is_in_cooldown(model):
                return model
        return None


def _is_rate_or_overload(exc: Exception) -> bool:
    if isinstance(exc, APIStatusError):
        return getattr(exc, "status_code", None) in (429, 503)
    text = str(exc).lower()
    return any(token in text for token in ("rate limit", "overloaded", "unavailable", "429", "503", "resource exhausted"))


def _gemini_chain(role: str, model: Optional[str], temperature: float, api_key: Optional[str]) -> list[BaseLLMClient]:
    fast = role in ("outline", "critic", "hook")
    primary = model or (settings.GEMINI_MODEL_FAST if fast else settings.GEMINI_MODEL_WRITER)
    chain = [primary]
    for extra in settings.GEMINI_MODEL_FALLBACKS.split(","):
        extra = extra.strip()
        if extra and extra not in chain:
            chain.append(extra)
    key = api_key or settings.GEMINI_API_KEY
    timeout = settings.GEMINI_REQUEST_TIMEOUT_SECONDS
    clients: list[BaseLLMClient] = [GeminiLLMClient(api_key=key, model=m, temperature=temperature, timeout=timeout) for m in chain]
    groq_key = (settings.GROQ_API_KEY or "").strip()
    if groq_key:
        clients.append(GroqLLMClient(api_key=groq_key, model=(settings.GROQ_MODEL or "openai/gpt-oss-20b").strip(), temperature=temperature))
    return clients


def get_llm_client(
    provider: Optional[str] = None,
    api_key: Optional[str] = None,
    model: Optional[str] = None,
    temperature: Optional[float] = None,
    role: str = "writer",
) -> BaseLLMClient:
    """Factory: return the configured LLM client (Fallback chain for Gemini, single client for Anthropic)."""
    resolved_provider = (provider or settings.LLM_PROVIDER or "anthropic").strip().lower()
    resolved_temperature = settings.TEMPERATURE if temperature is None else temperature
    if resolved_provider == "gemini":
        return FallbackLLMClient(_gemini_chain(role, model, resolved_temperature, api_key), role=role)
    if model is None:
        model = settings.LLM_OUTLINE_MODEL if role in ("outline", "critic", "hook") else settings.LLM_WRITER_MODEL
    return AnthropicLLMClient(api_key=api_key or settings.ANTHROPIC_API_KEY, model=model, temperature=resolved_temperature)


__all__ = [
    "AnthropicLLMClient",
    "BaseLLMClient",
    "FallbackLLMClient",
    "GeminiLLMClient",
    "GroqLLMClient",
    "get_llm_client",
]
