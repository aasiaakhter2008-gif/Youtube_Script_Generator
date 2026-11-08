"""Gemini embeddings client: Google's REST embedding API, batched, with tenacity retries on 429/503.

Model default is the current Gemini embedding model (gemini-embedding-2, stable since April 2026).
The API key is read from settings.GEMINI_API_KEY and never logged or hardcoded.
"""

import logging
from typing import Optional

import httpx
from tenacity import retry, retry_if_exception_type, stop_after_attempt, wait_exponential

from app.core.config import settings

logger = logging.getLogger("youtube_script_generator")

_EMBED_BASE_URL = "https://generativelanguage.googleapis.com/v1beta"


class EmbeddingError(RuntimeError):
    """Raised when embedding generation fails after all retries."""


class _RetryableEmbeddingError(EmbeddingError):
    """429/503 only — retrying permanent client errors is pointless."""


class GeminiEmbeddings:
    """Batched text embeddings via Google's embedding REST API (embedContent/batchEmbedContents)."""

    def __init__(self, api_key: Optional[str] = None, model: Optional[str] = None, timeout: float = 60.0) -> None:
        self._api_key = api_key if api_key is not None else settings.GEMINI_API_KEY
        self._model = (model or settings.EMBEDDING_MODEL or "gemini-embedding-2").strip()
        self.timeout = timeout
        self._client: Optional[httpx.AsyncClient] = None
        self._dims: Optional[int] = None

    # ---------- public API ----------

    async def dimension(self) -> int:
        """Detect the embedding dimension dynamically by embedding a probe string (cached)."""
        if self._dims is not None:
            return self._dims
        probe = await self.embed_documents(["__dimension_probe__"])
        if not probe:
            raise EmbeddingError("Embedding probe returned no vectors")
        self._dims = len(probe[0])
        return self._dims

    async def embed(self, texts: list[str], *, is_query: bool = False) -> list[list[float]]:
        """Embed a list of texts, returning one vector per input (same order)."""
        if not texts:
            return []
        clean = [str(t) for t in texts]
        out: list[list[float]] = []
        for i in range(0, len(clean), 100):
            out.extend(await self._embed_batch(clean[i : i + 100], is_query=is_query))
        return out

    async def embed_documents(self, texts: list[str], title: Optional[str] = None) -> list[list[float]]:
        return await self.embed(texts, is_query=False)

    async def embed_query(self, text: str) -> list[float]:
        vectors = await self.embed([text], is_query=True)
        if not vectors:
            raise EmbeddingError("Query embedding returned no vectors")
        return vectors[0]

    # ---------- internals ----------

    def _prepare(self, text: str, *, is_query: bool) -> str:
        model = self._model.lower()
        if "embedding-2" in model:
            if is_query:
                return f"task: search result | query: {text}"
            return f"title: none | text: {text}"
        # embedding-001 style: text itself stays plain; task_type set in the request
        return text

    def _is_v2(self) -> bool:
        return "embedding-2" in self._model.lower()

    async def _embed_batch(self, texts: list[str], *, is_query: bool) -> list[list[float]]:
        requests = []
        for text in texts:
            request: dict = {"model": f"models/{self._model}", "content": {"parts": [{"text": self._prepare(text, is_query=is_query)}]}}
            if not self._is_v2():
                request["taskType"] = "RETRIEVAL_QUERY" if is_query else "RETRIEVAL_DOCUMENT"
            requests.append(request)
        payload = {"requests": requests}
        response = await self._post(f"/models/{self._model}:batchEmbedContents", payload)
        embeddings = (response or {}).get("embeddings") or []
        vectors: list[list[float]] = []
        for entry in embeddings:
            values = (entry or {}).get("values") or []
            vectors.append([float(v) for v in values])
        if len(vectors) != len(texts):
            raise EmbeddingError(f"Embedding API returned {len(vectors)} vectors for {len(texts)} inputs")
        return vectors

    @retry(
        retry=retry_if_exception_type(_RetryableEmbeddingError),
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=1, max=8),
        reraise=True,
    )
    async def _post(self, path: str, payload: dict) -> dict:
        client = self._get_client()
        response = await client.post(
            f"{_EMBED_BASE_URL}{path}",
            headers={"x-goog-api-key": self._api_key, "Content-Type": "application/json"},
            json=payload,
        )
        if response.status_code in (429, 503):
            # Retryable per Google docs (rate limits / high demand); do not log payload (may contain user text).
            raise _RetryableEmbeddingError(f"Gemini embedding temporarily unavailable ({response.status_code})")
        if response.status_code >= 400:
            detail = ""
            try:
                body = response.json()
                detail = str((body.get("error") or {}).get("message") or body)[:300]
            except Exception:
                detail = response.text[:300]
            # 401/403 are permanent auth errors; retrying them is useless.
            raise EmbeddingError(f"Embedding API error {response.status_code}: {detail}")
        try:
            return response.json()
        except Exception as exc:
            raise EmbeddingError(f"Embedding API returned invalid JSON: {exc}") from exc

    def _get_client(self) -> httpx.AsyncClient:
        if self._client is None:
            self._client = httpx.AsyncClient(timeout=self.timeout)
        return self._client

    async def aclose(self) -> None:
        if self._client is not None:
            await self._client.aclose()
            self._client = None


_embeddings: Optional[GeminiEmbeddings] = None


def get_embeddings_service() -> GeminiEmbeddings:
    global _embeddings
    if _embeddings is None:
        _embeddings = GeminiEmbeddings()
    return _embeddings


def reset_embeddings_service() -> None:
    """Test hook: drop the cached embeddings client."""
    global _embeddings
    _embeddings = None
