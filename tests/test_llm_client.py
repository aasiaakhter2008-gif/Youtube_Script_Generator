import httpx
import pytest
from openai import RateLimitError
from pydantic import BaseModel

from app.core.config import settings
from app.services.llm_client import AnthropicLLMClient, BaseLLMClient, FallbackLLMClient, GeminiLLMClient, get_llm_client


class SampleOut(BaseModel):
    answer: str


class FakeGeminiMessage:
    def __init__(self, content) -> None:
        self.content = content


class FakeGeminiChoice:
    def __init__(self, content) -> None:
        self.message = FakeGeminiMessage(content)


class FakeGeminiCompletion:
    def __init__(self, content) -> None:
        self.choices = [FakeGeminiChoice(content)]


class FakeGeminiCompletions:
    def __init__(self, responses: list) -> None:
        self.responses = list(responses)
        self.calls = 0

    async def create(self, **kwargs):
        index = min(self.calls, len(self.responses) - 1)
        self.calls += 1
        response = self.responses[index]
        if isinstance(response, Exception):
            raise response
        return FakeGeminiCompletion(response)


class FakeGeminiClient:
    def __init__(self, responses: list) -> None:
        self.chat = type("Chat", (), {})()
        self.chat.completions = FakeGeminiCompletions(responses)


def _make_gemini_llm(responses: list, **kwargs) -> GeminiLLMClient:
    client = GeminiLLMClient(api_key="test-key", model="gemini-2.5-flash", **kwargs)
    client.client = FakeGeminiClient(responses)  # type: ignore[assignment]
    return client


@pytest.mark.asyncio
async def test_gemini_client_returns_validated_model() -> None:
    llm = _make_gemini_llm(['{"answer": "42"}'])
    result = await llm.structured("prompt", SampleOut, tool_name="sample_out")
    assert isinstance(result, SampleOut)
    assert result.answer == "42"


@pytest.mark.asyncio
async def test_gemini_client_strips_json_fences() -> None:
    llm = _make_gemini_llm(["```json\n{\"answer\": \"42\"}\n```"])
    result = await llm.structured("prompt", SampleOut, tool_name="sample_out")
    assert isinstance(result, SampleOut)
    assert result.answer == "42"


@pytest.mark.asyncio
async def test_gemini_client_retries_once_on_invalid_json() -> None:
    llm = _make_gemini_llm(['not valid json', '{"answer": "42"}'], max_retries=2, backoff_base=0.01)
    result = await llm.structured("prompt", SampleOut, tool_name="sample_out")
    assert result.answer == "42"
    assert llm.client.chat.completions.calls == 2


@pytest.mark.asyncio
async def test_gemini_client_raises_readable_error_on_rate_limit() -> None:
    request = httpx.Request("POST", "https://generativelanguage.googleapis.com/v1beta/openai/chat/completions")
    response = httpx.Response(status_code=429, request=request)
    rate_limit_error = RateLimitError("Rate limit exceeded for gemini", response=response, body={"error": {}})
    llm = _make_gemini_llm([rate_limit_error], max_retries=2, backoff_base=0.01)
    with pytest.raises(RuntimeError, match="Gemini rate limit exceeded"):
        await llm.structured("prompt", SampleOut, tool_name="sample_out")


def test_get_llm_client_returns_gemini_chain_when_provider_is_gemini(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "LLM_PROVIDER", "gemini")
    client = get_llm_client()
    assert isinstance(client, FallbackLLMClient)
    assert any(isinstance(c, GeminiLLMClient) for c in client.clients)


def test_get_llm_client_gemini_role_models(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "LLM_PROVIDER", "gemini")

    outline_client = get_llm_client(role="outline")
    assert isinstance(outline_client, FallbackLLMClient)
    assert isinstance(outline_client.clients[0], GeminiLLMClient)
    assert outline_client.model == settings.GEMINI_MODEL_FAST

    writer_client = get_llm_client(role="writer")
    assert isinstance(writer_client, FallbackLLMClient)
    assert writer_client.model == settings.GEMINI_MODEL_WRITER

    chain_models = [c.model for c in writer_client.clients]

    expected = [
        m.strip()
        for m in settings.GEMINI_MODEL_FALLBACKS.split(",")
        if m.strip() and m.strip() != settings.GEMINI_MODEL_WRITER
    ]

    assert chain_models[:len(expected) + 1] == [
        settings.GEMINI_MODEL_WRITER,
        *expected,
    ]

    if settings.GROQ_API_KEY:
        assert chain_models[-1] == (
            settings.GROQ_MODEL or "openai/gpt-oss-20b"
        ).strip()


def test_get_llm_client_defaults_to_anthropic_provider(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "LLM_PROVIDER", "anthropic")
    client = get_llm_client()
    assert isinstance(client, AnthropicLLMClient)
    assert isinstance(client, BaseLLMClient)


def test_get_llm_client_anthropic_provider_returns_anthropic_client(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "LLM_PROVIDER", "anthropic")
    client = get_llm_client()
    assert isinstance(client, AnthropicLLMClient)
