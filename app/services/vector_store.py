"""Vector store abstraction for embeddings.

- QdrantVectorStore: official qdrant-client async API (AsyncQdrantClient).
- InMemoryVectorStore: numpy-based fallback used when QDRANT_URL is not set (no persistence across restarts).

Every record carries user_id / workspace_id / voice_profile_id / source / chunk_index in its payload.
Every search filters by user/workspace so users never see each other's data.
"""

import logging
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, Optional, Sequence

import numpy as np
from qdrant_client import AsyncQdrantClient, models

from app.core.config import settings

logger = logging.getLogger("youtube_script_generator")

_COLLECTION_NAME = "script_chunks"


@dataclass
class VectorChunk:
    id: str
    text: str
    vector: list[float]
    metadata: dict[str, Any] = field(default_factory=dict)

    def merged_payload(self) -> dict[str, Any]:
        payload = {"text": self.text}
        payload.update(self.metadata or {})
        return payload


@dataclass
class SearchResult:
    id: str
    text: str
    score: float
    metadata: dict[str, Any] = field(default_factory=dict)


class VectorStore(ABC):
    """Async interface implemented by QdrantVectorStore and InMemoryVectorStore."""

    provider: str = "memory"

    @property
    @abstractmethod
    def collection_name(self) -> str:
        raise NotImplementedError

    @abstractmethod
    async def ensure_collection(self, dim: int) -> None:
        """Create the collection if it does not exist (cosine distance) and payload indexes."""
        raise NotImplementedError

    @abstractmethod
    async def upsert(self, chunks: Sequence[VectorChunk]) -> int:
        raise NotImplementedError

    @abstractmethod
    async def search(
        self,
        query_vector: Sequence[float],
        *,
        top_k: int = 5,
        filters: Optional[dict[str, Any]] = None,
    ) -> list[SearchResult]:
        raise NotImplementedError

    @abstractmethod
    async def delete(
        self,
        *,
        ids: Optional[Sequence[str]] = None,
        filters: Optional[dict[str, Any]] = None,
    ) -> int:
        raise NotImplementedError

    @abstractmethod
    async def status(self) -> dict[str, Any]:
        """Collection status info for /health/vector (never includes URL or API key)."""
        raise NotImplementedError


class QdrantVectorStore(VectorStore):
    provider = "qdrant"

    def __init__(self, url: str, api_key: Optional[str] = None, prefix: Optional[str] = None) -> None:
        self._client = AsyncQdrantClient(url=url, api_key=api_key or None, timeout=30.0)
        self.prefix = (prefix or settings.QDRANT_COLLECTION_PREFIX or "ysg").strip() or "ysg"
        self._collection = f"{self.prefix}_{_COLLECTION_NAME}"

    @property
    def collection_name(self) -> str:
        return self._collection

    async def ensure_collection(self, dim: int) -> None:
        exists = await self._client.collection_exists(self._collection)
        if not exists:
            await self._client.create_collection(
                collection_name=self._collection,
                vectors_config=models.VectorParams(size=int(dim), distance=models.Distance.COSINE),
            )
            logger.info("qdrant collection created", extra={"collection": self._collection})
        # Qdrant requires payload indexes for every field used in query filters.
        for field_name in ("user_id", "workspace_id", "voice_profile_id", "source"):
            try:
                await self._client.create_payload_index(
                    collection_name=self._collection,
                    field_name=field_name,
                    field_schema=models.PayloadSchemaType.KEYWORD,
                )
            except Exception as exc:  # index may already exist; non-fatal
                logger.debug("payload index ensure skipped", extra={"field": field_name, "error": str(exc)[:200]})

    async def upsert(self, chunks: Sequence[VectorChunk]) -> int:
        if not chunks:
            return 0
        points = [
            models.PointStruct(id=chunk.id, vector=chunk.vector, payload=chunk.merged_payload())
            for chunk in chunks
        ]
        await self._client.upsert(collection_name=self._collection, points=points)
        return len(points)

    async def search(
        self,
        query_vector: Sequence[float],
        *,
        top_k: int = 5,
        filters: Optional[dict[str, Any]] = None,
    ) -> list[SearchResult]:
        query_filter = self._build_filter(filters)
        response = await self._client.query_points(
            collection_name=self._collection,
            query=list(query_vector),
            limit=int(top_k),
            query_filter=query_filter,
            with_payload=True,
        )
        results: list[SearchResult] = []
        for point in response.points:
            payload = point.payload or {}
            results.append(
                SearchResult(
                    id=str(point.id),
                    text=str(payload.get("text") or ""),
                    score=float(point.score or 0.0),
                    metadata={k: v for k, v in payload.items() if k != "text"},
                )
            )
        return results

    async def delete(
        self,
        *,
        ids: Optional[Sequence[str]] = None,
        filters: Optional[dict[str, Any]] = None,
    ) -> int:
        if ids:
            selector = models.PointIdsList(points=list(ids))
            await self._client.delete(collection_name=self._collection, points_selector=selector)
            return len(list(ids))
        if filters:
            selector = models.FilterSelector(filter=self._build_filter(filters))
            await self._client.delete(collection_name=self._collection, points_selector=selector)
            return -1  # qdrant does not report count for filtered deletes
        return 0

    async def status(self) -> dict[str, Any]:
        try:
            exists = await self._client.collection_exists(self._collection)
            if not exists:
                return {"provider": self.provider, "collection": self._collection, "collection_status": "missing", "vectors_count": 0}
            count = await self._client.count(collection_name=self._collection, exact=True)
            return {
                "provider": self.provider,
                "collection": self._collection,
                "collection_status": "created",
                "vectors_count": int(getattr(count, "count", 0) or 0),
            }
        except Exception as exc:
            return {
                "provider": self.provider,
                "collection": self._collection,
                "collection_status": "error",
                "error": str(exc)[:150],
            }

    @staticmethod
    def _build_filter(filters: Optional[dict[str, Any]]) -> Optional[models.Filter]:
        if not filters:
            return None
        conditions = [
            models.FieldCondition(key=str(key), match=models.MatchValue(value=value))
            for key, value in filters.items()
            if value is not None
        ]
        if not conditions:
            return None
        return models.Filter(must=conditions)


class InMemoryVectorStore(VectorStore):
    provider = "memory"

    def __init__(self, prefix: Optional[str] = None) -> None:
        self.prefix = (prefix or settings.QDRANT_COLLECTION_PREFIX or "ysg").strip() or "ysg"
        self._collection = f"{self.prefix}_{_COLLECTION_NAME}"
        self._dims: Optional[int] = None
        self._records: dict[str, VectorChunk] = {}

    @property
    def collection_name(self) -> str:
        return self._collection

    async def ensure_collection(self, dim: int) -> None:
        self._dims = int(dim)
        return None

    async def upsert(self, chunks: Sequence[VectorChunk]) -> int:
        for chunk in chunks:
            self._records[chunk.id] = chunk
        return len(list(chunks))

    async def search(
        self,
        query_vector: Sequence[float],
        *,
        top_k: int = 5,
        filters: Optional[dict[str, Any]] = None,
    ) -> list[SearchResult]:
        q = np.asarray(list(query_vector), dtype=np.float32)
        norm = float(np.linalg.norm(q))
        if norm == 0.0:
            q = q  # avoid division by zero; cosine sim falls back to 0
        scored: list[tuple[float, VectorChunk]] = []
        for record in self._records.values():
            if filters and not _matches(record.metadata, filters):
                continue
            v = np.asarray(record.vector, dtype=np.float32)
            sim = float(np.dot(q, v) / ((norm * float(np.linalg.norm(v))) + 1e-12))
            scored.append((sim, record))
        scored.sort(key=lambda item: item[0], reverse=True)
        return [
            SearchResult(id=chunk.id, text=chunk.text, score=sim, metadata=dict(chunk.metadata))
            for sim, chunk in scored[: max(1, int(top_k))]
        ]

    async def delete(
        self,
        *,
        ids: Optional[Sequence[str]] = None,
        filters: Optional[dict[str, Any]] = None,
    ) -> int:
        to_remove: list[str] = []
        if ids:
            to_remove.extend(str(i) for i in ids)
        if filters:
            for rec_id, chunk in self._records.items():
                if _matches(chunk.metadata, filters):
                    to_remove.append(rec_id)
        for rec_id in dict.fromkeys(to_remove):
            self._records.pop(rec_id, None)
        return len(to_remove)

    async def status(self) -> dict[str, Any]:
        return {
            "provider": self.provider,
            "collection": self._collection,
            "collection_status": "created" if self._dims else "uninitialized",
            "vectors_count": len(self._records),
        }


def _matches(metadata: dict[str, Any], filters: dict[str, Any]) -> bool:
    for key, value in filters.items():
        if value is not None and metadata.get(key) != value:
            return False
    return True


_store: Optional[VectorStore] = None


def get_vector_store() -> VectorStore:
    """Return the configured vector store (Qdrant if QDRANT_URL is set, else in-memory with a warning)."""
    global _store
    if _store is not None:
        return _store
    url = (settings.QDRANT_URL or "").strip()
    if url:
        try:
            _store = QdrantVectorStore(url=url, api_key=(settings.QDRANT_API_KEY or "").strip() or None)
            logger.info("vector store configured", extra={"provider": "qdrant"})
            return _store
        except Exception as exc:  # pragma: no cover - construction-time failures
            logger.warning("Qdrant init failed; using in-memory vector store", extra={"error": str(exc)[:200]})
            _store = InMemoryVectorStore()
            return _store
    logger.warning("QDRANT_URL is not set — using in-memory vector store (data will not persist across restarts)")
    _store = InMemoryVectorStore()
    return _store


def reset_vector_store() -> None:
    """Test hook: drop the cached vector store so the next call re-reads settings."""
    global _store
    _store = None


__all__ = [
    "InMemoryVectorStore",
    "QdrantVectorStore",
    "SearchResult",
    "VectorChunk",
    "VectorStore",
    "get_vector_store",
    "reset_vector_store",
]
