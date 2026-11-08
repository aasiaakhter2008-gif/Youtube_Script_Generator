import logging
from typing import Optional
from uuid import uuid4

from app.agents.gap import CompetitorGapAgent
from app.pipeline.state import PipelineState
from app.schemas.competitor import CompetitorGap, CompetitorVideo
from app.services.embeddings import get_embeddings_service
from app.services.security_utils import sanitize_untrusted
from app.services.vector_store import VectorChunk, get_vector_store
from app.services.voice_profiles import chunk_text

logger = logging.getLogger("youtube_script_generator")

_SIMILARITY_THRESHOLD = 0.78


class CompetitorService:
    """Competitor gap analysis: fetch competitor signals, cluster coverage via the vector store, find gaps."""

    def __init__(self, gap_agent: CompetitorGapAgent) -> None:
        self.gap_agent = gap_agent

    async def analyze(self, urls: list, *, user_id: str = "global", workspace_id: str = "default") -> Optional[CompetitorGap]:
        videos: list[CompetitorVideo] = []
        for url in urls or []:
            videos.append(await self._fetch_video(url))
        clusters = await self._store_and_cluster(videos, user_id=user_id, workspace_id=workspace_id)
        try:
            state = await self.gap_agent.run(
                PipelineState(job_id="competitors", status="running"),
                competitor_videos=videos,
                competitor_clusters=clusters,
            )
            return state.gap_analysis
        except Exception:
            logger.exception("competitor gap analysis failed")
            return CompetitorGap(competitors=[video.url for video in videos], gaps=[], suggestions=[])

    async def _fetch_video(self, url: str):
        video = {"url": url, "title": f"Competitor video: {url}", "channel": "unknown"}
        # Real implementation plugs in YouTube transcript / metadata providers here.
        return video

    @staticmethod
    def _transcript_text(video) -> str:
        if isinstance(video, dict):
            raw = " ".join(str(video.get(key) or "") for key in ("title", "channel", "description", "transcript")).strip()
        else:
            raw = f"{getattr(video, 'title', '')} {getattr(video, 'channel', '')}".strip()
        return sanitize_untrusted(raw)

    async def _store_and_cluster(self, videos: list, *, user_id: str, workspace_id: str) -> list[dict]:
        """Embed competitor transcripts into the shared vector store; cluster coverage by searching the store."""
        try:
            chunks: list[dict] = []
            for video in videos:
                text = self._transcript_text(video)
                for i, chunk in enumerate(chunk_text(text)):
                    chunks.append({"id": str(uuid4()), "video": video, "index": i, "text": chunk})
            if not chunks:
                return []
            embeddings = get_embeddings_service()
            vectors = await embeddings.embed_documents([c["text"] for c in chunks])
            store = get_vector_store()
            dim = len(vectors[0]) if vectors else 0
            if not dim:
                return []
            await store.ensure_collection(dim)
            records = [
                VectorChunk(
                    id=c["id"],
                    text=c["text"],
                    vector=vectors[i],
                    metadata={
                        "user_id": user_id,
                        "workspace_id": workspace_id,
                        "voice_profile_id": None,
                        "source": "competitor",
                        "chunk_index": c["index"],
                        "video_url": (c["video"].get("url") if isinstance(c["video"], dict) else getattr(c["video"], "url", "")) or "",
                        "video_title": (c["video"].get("title") if isinstance(c["video"], dict) else getattr(c["video"], "title", "")) or "",
                    },
                )
                for i, c in enumerate(chunks)
            ]
            await store.upsert(records)
            index_by_id = {c["id"]: i for i, c in enumerate(chunks)}
            hits = await self._search_all(store, records, vectors, user_id=user_id, workspace_id=workspace_id)
            parent = list(range(len(chunks)))

            def find(i: int) -> int:
                while parent[i] != i:
                    parent[i] = parent[parent[i]]
                    i = parent[i]
                return i

            def union(i: int, j: int) -> None:
                ri, rj = find(i), find(j)
                if ri != rj:
                    parent[ri] = rj

            for i, hit_list in enumerate(hits):
                for hit in hit_list:
                    j = index_by_id.get(hit.id)
                    if j is not None and hit.score >= _SIMILARITY_THRESHOLD:
                        union(i, j)
            groups: dict[int, list[int]] = {}
            for i in range(len(chunks)):
                groups.setdefault(find(i), []).append(i)
            return [self._cluster_dict([chunks[j] for j in members]) for members in groups.values()]
        except Exception as exc:
            logger.warning("competitor embedding/storage failed; continuing without clusters", extra={"error": str(exc)[:200]})
            return []

    async def _search_all(self, store, records: list[VectorChunk], vectors: list[list[float]], *, user_id: str, workspace_id: str):
        """Search the shared store for the nearest competitor chunks for each stored chunk."""
        results = []
        for i, record in enumerate(records):
            hits = await store.search(
                vectors[i],
                top_k=min(len(records), 20),
                filters={"user_id": user_id, "workspace_id": workspace_id, "source": "competitor"},
            )
            results.append(hits)
        return results

    @staticmethod
    def _cluster_dict(members: list[dict]) -> dict:
        items = []
        for chunk in members:
            video = chunk["video"]
            url = video.get("url") if isinstance(video, dict) else getattr(video, "url", "")
            title = video.get("title") if isinstance(video, dict) else getattr(video, "title", "")
            items.append({"text": chunk["text"], "url": url or "", "title": title or ""})
        return {"texts": [item["text"] for item in items], "items": items}


competitor_service = CompetitorService(CompetitorGapAgent())
