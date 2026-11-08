"""Resilience: fallback chain, cooldown, cache, rate limiter, resume-from-step (no real API calls)."""

import time

import httpx
import pytest
from openai import RateLimitError
from pydantic import BaseModel

import app.services.llm_runtime as llm_runtime
from app.services.llm_client import FallbackLLMClient, GeminiLLMClient
from app.core.config import settings
from app.pipeline.runner import Pipeline
from app.schemas.script import (
    ChosenHook,
    CriticAssessment,
    CriticResult,
    Outline,
    OutlineSection,
    ScriptRequest,
    SectionType,
    WriterSection,
)
from app.agents.base import BaseAgent


class SampleOut(BaseModel):
    answer: str


def _outline() -> Outline:
    section = OutlineSection(section_type=SectionType.HOOK, title="Deep sleep", estimated_duration_seconds=15)
    return Outline(hook=section, intro=section, main_points=[section], retention_loop=section, cta=section, outro=section)


def _critique(passed: bool) -> CriticResult:
    return CriticResult(
        assessment=CriticAssessment(
            hook_strength=9.0 if passed else 4.0,
            pacing=9.0 if passed else 4.0,
            clarity=9.0 if passed else 5.0,
            repetition=9.0 if passed else 7.0,
            feedback="pass" if passed else "revise",
            passed=passed,
        ),
        weak_sections=[],
    )


def _writer_section() -> WriterSection:
    return WriterSection(section_type=SectionType.HOOK, title="Hook", content="Sleep is a superpower.", b_roll_cues=[], on_screen_text=[], word_count=4)


class _FakeSDKCompletions:
    def __init__(self, responses: list) -> None:
        self.responses = list(responses)
        self.calls = 0

    async def create(self, **kwargs):
        index = min(self.calls, len(self.responses) - 1)
        self.calls += 1
        response = self.responses[index]
        if isinstance(response, Exception):
            raise response
        return type("C", (), {"choices": [type("Ch", (), {"message": type("M", (), {"content": response})()})()]})()


class _FakeSDKClient:
    def __init__(self, responses: list) -> None:
        self.chat = type("Chat", (), {})()
        self.chat.completions = _FakeSDKCompletions(responses)


def _gemini_with_responses(model: str, responses: list, **kwargs) -> GeminiLLMClient:
    client = GeminiLLMClient(api_key="test-key", model=model, **kwargs)
    client.client = _FakeSDKClient(responses)
    return client


@pytest.fixture(autouse=True)
def _reset_runtime():
    llm_runtime.reset_llm_runtime()
    yield
    llm_runtime.reset_llm_runtime()


# ----------------------------- retry, fallback, cooldown -----------------------------


@pytest.mark.asyncio
async def test_fallback_uses_next_model_after_first_exhausted(monkeypatch) -> None:
    monkeypatch.setattr(settings, "LLM_CACHE_TTL_SECONDS", 0)
    request = httpx.Request("POST", "https://generativelanguage.googleapis.com/v1beta/openai/chat/completions")
    response = httpx.Response(status_code=503, request=request, headers={"retry-after": "5"})
    m1 = _gemini_with_responses(
        "gemini-3.8-flash",
        [RateLimitError("busy", response=response, body={"error": {}})] * 2,
        max_retries=2,
        backoff_base=0.01,
    )
    m2 = _gemini_with_responses("gemini-3.6-flash", ['{"answer": "ok"}'], max_retries=1, backoff_base=0.01)
    chain = FallbackLLMClient([m1, m2])
    result = await chain.structured("prompt", SampleOut, tool_name="sample")
    assert result.answer == "ok"
    assert m1.client.chat.completions.calls == 2
    assert m2.client.chat.completions.calls == 1


@pytest.mark.asyncio
async def test_all_models_fail_raises_and_marks_cooldown(monkeypatch) -> None:
    monkeypatch.setattr(settings, "LLM_CACHE_TTL_SECONDS", 0)
    request = httpx.Request("POST", "https://generativelanguage.googleapis.com/v1beta/openai/chat/completions")
    response = httpx.Response(status_code=429, request=request, headers={"retry-after": "42"})
    err = RateLimitError("rate limited", response=response, body={"error": {}})
    m1 = _gemini_with_responses("gemini-3.8-flash", [err, err], max_retries=2, backoff_base=0.01)
    m2 = _gemini_with_responses("gemini-3.6-flash", [err, err], max_retries=2, backoff_base=0.01)
    chain = FallbackLLMClient([m1, m2])
    with pytest.raises(RuntimeError, match="All LLM providers busy"):
        await chain.structured("prompt", SampleOut, tool_name="sample")
    assert llm_runtime.is_in_cooldown("gemini-3.8-flash")
    assert llm_runtime.is_in_cooldown("gemini-3.6-flash")
    # a cooled-down model must not be hit again
    m1_calls = m1.client.chat.completions.calls
    m2_calls = m2.client.chat.completions.calls
    with pytest.raises(RuntimeError):
        await chain.structured("different prompt", SampleOut, tool_name="sample")
    assert m1.client.chat.completions.calls == m1_calls
    assert m2.client.chat.completions.calls == m2_calls


@pytest.mark.asyncio
async def test_cache_hit_avoids_duplicate_calls(monkeypatch) -> None:
    monkeypatch.setattr(settings, "LLM_CACHE_TTL_SECONDS", 300)
    m = _gemini_with_responses("gemini-3.8-flash", ['{"answer": "42"}'], max_retries=1, backoff_base=0.01)
    chain = FallbackLLMClient([m])
    first = await chain.structured("p", SampleOut, tool_name="t")
    second = await chain.structured("p", SampleOut, tool_name="t")
    assert first.answer == second.answer == "42"
    assert m.client.chat.completions.calls == 1


# ----------------------------- token bucket -----------------------------


@pytest.mark.asyncio
async def test_token_bucket_burst_then_waits(monkeypatch) -> None:
    monkeypatch.setattr(settings, "LLM_REQUESTS_PER_MINUTE", 120)  # 120/min => 2 tokens per second
    bucket = llm_runtime.TokenBucket(settings.LLM_REQUESTS_PER_MINUTE)
    bucket.tokens = 0.0  # simulate exhaustion
    start = time.monotonic()
    await bucket.acquire()
    assert time.monotonic() - start >= 0.4


# ----------------------------- resume from last completed step -----------------------------


class _FakeOutlineAgent(BaseAgent):
    name = "outline"

    def __init__(self) -> None:
        self.calls = 0

    async def run(self, state, **kwargs):
        self.calls += 1
        state.outline = _outline()
        return state


class _FakeHookAgent(BaseAgent):
    name = "hook"

    def __init__(self) -> None:
        self.calls = 0

    async def run(self, state, **kwargs):
        self.calls += 1
        state.hooks = ChosenHook(text="Your brain detoxes while you sleep.", variations=[])
        return state


class _FakeWriterAgent(BaseAgent):
    name = "writer"

    def __init__(self) -> None:
        self.calls = 0
        self.fail = True

    async def run(self, state, **kwargs):
        self.calls += 1
        if self.fail:
            raise RuntimeError("boom")
        state.sections = [_writer_section()]
        return state


class _FakeCriticAgent(BaseAgent):
    name = "critic"

    def __init__(self) -> None:
        self.calls = 0

    async def run(self, state, **kwargs):
        self.calls += 1
        state.critic_feedback = _critique(True)
        return state


def _request() -> ScriptRequest:
    return ScriptRequest(topic="The Science of Sleep", duration_minutes=1, format="shorts")


@pytest.mark.asyncio
async def test_resume_skips_completed_steps() -> None:
    outline = _FakeOutlineAgent()
    hook = _FakeHookAgent()
    writer = _FakeWriterAgent()
    critic = _FakeCriticAgent()
    pipeline = Pipeline(
        outline_agent=outline,
        hook_agent=hook,
        writer_agent=writer,
        critic_agent=critic,
        steps=["outline", "hook", "writer", "critic"],
    )

    steps_seen: list[str] = []

    async def on_step(name, state):
        steps_seen.append(name)

    with pytest.raises(RuntimeError, match="boom"):
        await pipeline.run("job-1", _request(), steps=["outline", "hook", "writer"], on_step=on_step)

    assert steps_seen == ["outline", "hook"]
    assert outline.calls == 1
    assert hook.calls == 1

    writer.fail = False
    steps_seen.clear()
    state = await pipeline.run("job-1-resume", _request(), steps=["writer", "critic"], on_step=on_step)
    assert outline.calls == 1, "outline must not be re-run on resume"
    assert hook.calls == 1, "hook must not be re-run on resume"
    assert writer.calls == 2
    assert critic.calls == 1
    assert state.sections and state.critic_feedback is not None
