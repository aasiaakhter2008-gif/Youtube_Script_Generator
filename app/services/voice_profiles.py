"""Voice profiles: user writing style samples, embedded for retrieval.

Flow: chunk sample texts (~300-500 tokens with overlap) -> embed -> upsert to the shared vector store.
Any feature (writer agent, competitor gap analysis) can retrieve the most similar style chunks
for a query, filtered by user_id/workspace_id so users never see each other's data.
"""

import logging
from dataclasses import dataclass
from typing import Optional
from uuid import uuid4

from app.models.db import VoiceProfile, async_session
from app.services.embeddings import GeminiEmbeddings, get_embeddings_service
from app.services.vector_store import SearchResult, VectorChunk, get_vector_store

logger = logging.getLogger("youtube_script_generator")

# ~400 tokens at ~4 chars/token, with ~15% overlap
_CHUNK_MAX_CHARS = 1600
_CHUNK_OVERLAP_CHARS = 240


def chunk_text(text: str, *, max_chars: int = _CHUNK_MAX_CHARS, overlap: int = _CHUNK_OVERLAP_CHARS) -> list[str]:
    """Split text into overlapping character windows (~300-500 tokens)."""
    cleaned = " ".join(str(text).split())
    if not cleaned:
        return []
    step = max(1, max_chars - overlap)
    chunks: list[str] = []
    start = 0
    while start < len(cleaned):
        end = min(len(cleaned), start + max_chars)
        chunk = cleaned[start:end].strip()
        if chunk:
            chunks.append(chunk)
        if end >= len(cleaned):
            break
        start += step
    return chunks


@dataclass
class VoiceProfileResult:
    id: str
    name: str
    user_id: str
    workspace_id: str
    source: str
    chunk_count: int


def _profile_filters(user_id: Optional[str], workspace_id: Optional[str]) -> dict:
    filters = {"user_id": user_id or "global"}
    if workspace_id:
        filters["workspace_id"] = workspace_id
    return filters


class VoiceProfileService:
    def __init__(self, embeddings: Optional[GeminiEmbeddings] = None) -> None:
        self.embeddings = embeddings or get_embeddings_service()

    async def create(
        self,
        *,
        name: str,
        texts: list[str],
        user_id: str = "global",
        workspace_id: str = "default",
    ) -> VoiceProfileResult:
        """Persist a voice profile, embed its sample texts and upsert the chunks."""
        async with async_session() as session:
            profile = VoiceProfile(name=name, user_id=user_id, workspace_id=workspace_id, source="user")
            session.add(profile)
            await session.commit()
            await session.refresh(profile)
        try:
            chunk_count = await self._embed_and_store(profile.id, texts, user_id=user_id, workspace_id=workspace_id)
        except Exception as exc:
            logger.warning("voice profile embedding failed; profile kept without vectors", extra={"profile_id": profile.id, "error": str(exc)[:200]})
            chunk_count = 0
        return VoiceProfileResult(
            id=profile.id,
            name=profile.name,
            user_id=profile.user_id,
            workspace_id=profile.workspace_id,
            source=profile.source,
            chunk_count=chunk_count,
        )

    async def _embed_and_store(self, profile_id: str, texts: list[str], *, user_id: str, workspace_id: str) -> int:
        chunks = chunk_text("\n\n".join(texts))
        if not chunks:
            return 0
        vectors = await self.embeddings.embed_documents(chunks)
        store = get_vector_store()
        await store.ensure_collection(len(vectors[0]))
        records = [
            VectorChunk(
                id=str(uuid4()),
                text=chunk,
                vector=vectors[i],
                metadata={
                    "user_id": user_id,
                    "workspace_id": workspace_id,
                    "voice_profile_id": profile_id,
                    "source": "voice_profile",
                    "chunk_index": i,
                },
            )
            for i, chunk in enumerate(chunks)
        ]
        return await store.upsert(records)

    async def search(
        self,
        *,
        query: str,
        voice_profile_id: Optional[str] = None,
        top_k: int = 5,
        user_id: Optional[str] = None,
        workspace_id: Optional[str] = None,
    ) -> list[SearchResult]:
        query_vector = await self.embeddings.embed_query(query)
        filters = _profile_filters(user_id, workspace_id)
        filters["source"] = "voice_profile"
        if voice_profile_id:
            filters["voice_profile_id"] = voice_profile_id
        store = get_vector_store()
        await store.ensure_collection(len(query_vector))
        return await store.search(query_vector, top_k=top_k, filters=filters)

    async def delete(self, profile_id: str, *, user_id: Optional[str] = None, workspace_id: Optional[str] = None) -> bool:
        """Delete the profile row and its vectors (best effort)."""
        async with async_session() as session:
            profile = await session.get(VoiceProfile, profile_id)
            if profile is None:
                return False
            uid = user_id or profile.user_id
            wid = workspace_id or profile.workspace_id
            filters = {"user_id": uid, "workspace_id": wid, "voice_profile_id": profile_id, "source": "voice_profile"}
            try:
                store = get_vector_store()
                await store.delete(filters=filters)
            except Exception as exc:
                logger.warning("vector delete failed for voice profile", extra={"profile_id": profile_id, "error": str(exc)[:200]})
            await session.delete(profile)
            await session.commit()
            return True

    async def get(self, profile_id: str):
        async with async_session() as session:
            return await session.get(VoiceProfile, profile_id)


voice_profile_service = VoiceProfileService()
