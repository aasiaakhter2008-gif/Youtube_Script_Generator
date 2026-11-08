"""Vector store + embeddings tests. Qdrant and embeddings are mocked; in-memory store tested for real."""

import logging

import pytest

import app.services.vector_store as vector_store_module
from app.core.config import settings
from app.services.embeddings import GeminiEmbeddings, EmbeddingError
from app.services.vector_store import InMemoryVectorStore, QdrantVectorStore, VectorChunk, get_vector_store, reset_vector_store
import app.services.voice_profiles as voice_profiles_module
from app.services.voice_profiles import VoiceProfileService, chunk_text


# ----------------------------- in-memory store -----------------------------


@pytest.mark.asyncio
async def test_inmemory_store_search_and_filters():
    store = InMemoryVectorStore(prefix="test")
    await store.ensure_collection(4)
    chunks = [
        VectorChunk(id="a", text="alpha", vector=[1.0, 0.0, 0.0, 0.0], metadata={"user_id": "user-1", "source": "voice_profile", "chunk_index": 0}),
        VectorChunk(id="b", text="beta", vector=[0.0, 1.0, 0.0, 0.0], metadata={"user_id": "user-2", "source": "voice_profile", "chunk_index": 0}),
        VectorChunk(id="c", text="gamma", vector=[0.9, 0.1, 0.0, 0.0], metadata={"user_id": "user-1", "source": "voice_profile", "chunk_index": 1}),
    ]
    assert await store.upsert(chunks) == 3

    # user-1 only: c should be more similar to query than b
    results = await store.search([1.0, 0.0, 0.0, 0.0], top_k=5, filters={"user_id": "user-1"})
    ids = [r.id for r in results]
    assert ids[0] == "a"
    assert "b" not in ids
    assert "c" in ids
    assert results[0].score >= results[-1].score

    # delete by id
    assert await store.delete(ids=["a"]) == 1
    remaining = await store.search([1.0, 0.0, 0.0, 0.0], top_k=5, filters={"user_id": "user-1"})
    assert "a" not in [r.id for r in remaining]

    # delete by filter
    assert await store.delete(filters={"user_id": "user-1"}) == 1
    remaining = await store.search([1.0, 0.0, 0.0, 0.0], top_k=5, filters={"user_id": "user-1"})
    assert remaining == []


@pytest.mark.asyncio
async def test_inmemory_search_without_filters_returns_all():
    store = InMemoryVectorStore(prefix="test")
    await store.ensure_collection(2)
    await store.upsert([
        VectorChunk(id="x", text="x", vector=[1.0, 0.0], metadata={"user_id": "u1"}),
        VectorChunk(id="y", text="y", vector=[0.0, 1.0], metadata={"user_id": "u2"}),
    ])
    results = await store.search([1.0, 0.0], top_k=10, filters=None)
    assert len(results) == 2


# ----------------------------- qdrant store (mocked client) -----------------------------


class _FakePoint:
    def __init__(self, id: str, score: float, payload: dict) -> None:
        self.id = id
        self.score = score
        self.payload = payload


class _FakeQueryPointsResponse:
    def __init__(self, points: list) -> None:
        self.points = points


class _FakeCount:
    def __init__(self, count: int) -> None:
        self.count = count


class FakeQdrantClient:
    def __init__(self, **kwargs) -> None:
        self.kwargs = kwargs
        self._exists = False
        self.created: list[dict] = []
        self.indexes: list[dict] = []
        self.upserted: list[dict] = []
        self.deleted: list[dict] = []
        self.query: dict | None = None

    async def collection_exists(self, collection_name: str) -> bool:
        return self._exists

    async def create_collection(self, **kwargs) -> None:
        self._exists = True
        self.created.append(kwargs)

    async def create_payload_index(self, **kwargs) -> None:
        self.indexes.append(kwargs)

    async def upsert(self, **kwargs) -> None:
        self.upserted.append(kwargs)

    async def query_points(self, **kwargs):
        self.query = kwargs
        return _FakeQueryPointsResponse(
            [_FakePoint("id-1", 0.92, {"text": "hello", "user_id": "user-1", "source": "voice_profile", "chunk_index": 0})]
        )

    async def delete(self, **kwargs) -> None:
        self.deleted.append(kwargs)

    async def count(self, **kwargs) -> _FakeCount:
        return _FakeCount(3)


@pytest.mark.asyncio
async def test_qdrant_store_mocked(monkeypatch):
    monkeypatch.setattr(vector_store_module, "AsyncQdrantClient", FakeQdrantClient)
    store = QdrantVectorStore(url="https://qdrant.example.internal", api_key="secret-key", prefix="ysg")

    await store.ensure_collection(4)
    fake_client = store._client
    assert fake_client.created, "create_collection should be called when the collection is missing"
    assert fake_client.created[0]["collection_name"] == "ysg_script_chunks"
    indexed = {idx["field_name"] for idx in fake_client.indexes}
    assert {"user_id", "workspace_id", "voice_profile_id"} <= indexed

    chunks = [
        VectorChunk(id="id-1", text="one", vector=[1.0, 0.0, 0.0, 0.0], metadata={"user_id": "user-1", "source": "voice_profile", "chunk_index": 0}),
        VectorChunk(id="id-2", text="two", vector=[0.0, 1.0, 0.0, 0.0], metadata={"user_id": "user-1", "source": "voice_profile", "chunk_index": 1}),
    ]
    assert await store.upsert(chunks) == 2
    assert fake_client.upserted[0]["collection_name"] == "ysg_script_chunks"

    results = await store.search([1.0, 0.0, 0.0, 0.0], top_k=3, filters={"user_id": "user-1"})
    assert results[0].text == "hello"
    assert results[0].score == pytest.approx(0.92)
    assert results[0].metadata["user_id"] == "user-1"
    assert fake_client.query is not None
    assert fake_client.query["collection_name"] == "ysg_script_chunks"
    assert fake_client.query["query_filter"] is not None

    count = await store.delete(filters={"user_id": "user-1"})
    assert count == -1
    assert fake_client.deleted, "filtered delete should reach the client"

    status = await store.status()
    assert status["provider"] == "qdrant"
    assert status["collection_status"] == "created"
    assert status["vectors_count"] == 3
    # never leak the URL or key
    assert "qdrant.example.internal" not in str(status)
    assert "secret-key" not in str(status)


# ----------------------------- embeddings (mocked HTTP) -----------------------------


@pytest.mark.asyncio
async def test_embeddings_batches_and_dimension(monkeypatch):
    calls: list[dict] = []

    async def fake_post(self, path: str, payload: dict) -> dict:
        calls.append({"path": path, "payload": payload})
        batch_size = len(payload["requests"])
        return {"embeddings": [{"values": [1.0, 0.0, 0.0, 0.0]} for _ in range(batch_size)]}

    monkeypatch.setattr(GeminiEmbeddings, "_post", fake_post)
    embeddings = GeminiEmbeddings(api_key="test-key", model="gemini-embedding-2")

    vectors = await embeddings.embed_documents([f"doc {i}" for i in range(250)])
    assert len(vectors) == 250
    assert calls, "batchEmbedContents should be called"
    assert sum(len(c["payload"]["requests"]) for c in calls) == 250

    query = await embeddings.embed_query("hello world")
    assert query == [1.0, 0.0, 0.0, 0.0]

    dim = await embeddings.dimension()
    assert dim == 4


@pytest.mark.asyncio
async def test_embeddings_retryable_vs_permanent(monkeypatch):
    from app.services.embeddings import _RetryableEmbeddingError

    permanent_but_429 = GeminiEmbeddings(api_key="k", model="gemini-embedding-2")

    async def always_429(*args, **kwargs):
        raise _RetryableEmbeddingError("rate limit")

    monkeypatch.setattr(GeminiEmbeddings, "_post", always_429)
    with pytest.raises(EmbeddingError):
        await permanent_but_429.embed_documents(["x"])


# ----------------------------- fallback factory -----------------------------


def test_empty_qdrant_url_falls_back_to_memory(monkeypatch, caplog):
    monkeypatch.setattr(settings, "QDRANT_URL", "")
    monkeypatch.setattr(settings, "QDRANT_API_KEY", "")
    reset_vector_store()
    with caplog.at_level(logging.WARNING):
        store = get_vector_store()
    assert store.provider == "memory"
    assert "in-memory vector store" in caplog.text.lower()
    reset_vector_store()


# ----------------------------- voice profile service -----------------------------


class FakeEmbeddings:
    async def embed_documents(self, texts, title=None):
        vectors = []
        for text in texts:
            vec = [0.0] * 8
            for token in str(text).lower().split():
                vec[hash(token) % 8] += 1.0
            vectors.append(vec)
        return vectors

    async def embed_query(self, text):
        return (await self.embed_documents([text]))[0]

    async def dimension(self):
        return 8


class _FakeSession:
    def __init__(self, store: list) -> None:
        self._store = store

    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        return False

    def add(self, obj) -> None:
        self._store.append(obj)

    async def commit(self) -> None:
        return None

    async def refresh(self, obj) -> None:
        return None

    async def get(self, model, id):
        return next((p for p in self._store if p.id == id), None)

    async def delete(self, obj) -> None:
        self._store.remove(obj)


@pytest.mark.asyncio
async def test_voice_profile_create_search_delete(monkeypatch):
    db_rows: list = []

    def fake_session_factory():
        store = db_rows

        class _Ctx:
            async def __aenter__(self):
                return _FakeSession(store)

            async def __aexit__(self, *args):
                return False

        return _Ctx()

    monkeypatch.setattr(voice_profiles_module, "async_session", fake_session_factory)
    monkeypatch.setattr(voice_profiles_module, "get_embeddings_service", lambda: FakeEmbeddings())
    monkeypatch.setattr(settings, "QDRANT_URL", "")
    monkeypatch.setattr(settings, "QDRANT_API_KEY", "")
    reset_vector_store()
    store = get_vector_store()
    assert store.provider == "memory"

    service = VoiceProfileService(embeddings=FakeEmbeddings())

    texts = [
        "Short punchy sentences. No fluff. I always open with a bold claim.",
        "My videos keep a fast pace with pattern interrupts every thirty seconds.",
        "I end every video with a single clear call to action, never more.",
    ]
    result = await service.create(name="my voice", texts=texts, user_id="user-1", workspace_id="default")
    assert result.chunk_count >= 1
    assert result.id

    found = await service.search(query="rocket launch intro", voice_profile_id=result.id, user_id="user-1", workspace_id="default")
    assert found, "search should return stored style chunks"
    assert all(hit.metadata["voice_profile_id"] == result.id for hit in found)

    assert await service.delete(result.id, user_id="user-1", workspace_id="default") is True
    gone = await service.search(query="rocket launch intro", voice_profile_id=result.id, user_id="user-1", workspace_id="default")
    assert gone == []
    reset_vector_store()


def test_chunk_text_overlap():
    text = "word " * 2000
    chunks = chunk_text(text, max_chars=100, overlap=20)
    assert len(chunks) > 1
    assert chunks[0][:10] == text.strip()[:10]


# ----------------------------- writer style examples -----------------------------


@pytest.mark.asyncio
async def test_writer_injects_style_examples(monkeypatch):
    import app.agents.writer as writer_module
    from app.pipeline.state import PipelineState
    from app.schemas.script import ScriptRequest

    class FakeVoiceProfile:
        id = "vp-1"
        user_id = "user-1"
        workspace_id = "default"

    class FakeVoiceProfileService:
        async def get(self, profile_id):
            return FakeVoiceProfile() if profile_id == "vp-1" else None

        async def search(self, **kwargs):
            from app.services.vector_store import SearchResult

            return [SearchResult(id="c1", text="fast paced bold intros", score=0.9, metadata={"voice_profile_id": "vp-1"})]

    monkeypatch.setattr(voice_profiles_module, "voice_profile_service", FakeVoiceProfileService())
    monkeypatch.setattr(voice_profiles_module, "get_embeddings_service", lambda: FakeEmbeddings())

    captured: list[str] = []

    class FakeLLM:
        async def structured(self, prompt, schema, **kwargs):
            captured.append(prompt)
            from app.schemas.script import WriterSection

            return WriterSection(section_type="hook", title="t", content="content", b_roll_cues=[], on_screen_text=[], word_count=1)

    agent = writer_module.WriterAgent(llm=FakeLLM())
    state = PipelineState(
        job_id="j1",
        status="running",
        request=ScriptRequest(topic="The Science of Sleep", duration_minutes=1, format="shorts", voice_profile_id="vp-1"),
    )
    from app.schemas.script import Outline, OutlineSection

    section = OutlineSection(section_type="hook", title="Why we sleep", estimated_duration_seconds=15)
    state.outline = Outline(
        hook=section,
        intro=section,
        main_points=[section],
        retention_loop=section,
        cta=section,
        outro=section,
    )
    section_state = await agent.run(state, weak_sections=["hook"])
    assert captured, "writer should have called the LLM"
    assert "Style examples" in captured[0]
    assert "fast paced bold intros" in captured[0]
    assert section_state.sections
