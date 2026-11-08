from typing import Optional

from app.agents.base import BaseAgent
from app.pipeline.state import PipelineState
from app.schemas.competitor import CompetitorGap, CompetitorVideo, Gap
from app.services.llm_client import BaseLLMClient


class CompetitorGapAgent(BaseAgent):
    """Finds content gaps vs competitor channels/videos and suggests new angles."""

    name = "gap"

    def __init__(self, llm: BaseLLMClient = None) -> None:
        self.llm = llm

    async def run(self, state: PipelineState, **kwargs) -> PipelineState:
        videos = list(kwargs.get("competitor_videos") or [])
        clusters = list(kwargs.get("competitor_clusters") or [])
        gap = self._heuristic_gap(videos, clusters)
        state.gap_analysis = gap
        return state

    def _heuristic_gap(self, videos: list, clusters: Optional[list] = None) -> CompetitorGap:
        competitors: list[str] = []
        normalized: list[CompetitorVideo] = []
        for v in videos or []:
            if isinstance(v, dict):
                video = CompetitorVideo(url=str(v.get("url") or ""), title=str(v.get("title") or ""), channel=str(v.get("channel") or ""))
            else:
                video = v
            normalized.append(video)
            if video.url and video.url not in competitors:
                competitors.append(video.url)

        gaps: list[Gap] = []
        suggestions: list[str] = []
        if len(normalized) >= 2:
            titles = [v.title or v.url for v in normalized]
            for i, title in enumerate(titles):
                alone = all(self._token_overlap(title, t) < 0.3 for j, t in enumerate(titles) if i != j)
                if alone:
                    gaps.append(
                        Gap(
                            area="topic_coverage",
                            gap_description=f"Competitor video '{title}' covers a topic weakly covered elsewhere.",
                            suggested_angle=f"Deep-dive series on the subtopic of {title}",
                            difficulty=5,
                        )
                    )
                    suggestions.append(f"Create a follow-up video expanding on: {title}")
        if clusters:
            for cluster in clusters:
                groups = cluster.get("items") or []
                urls = {item.get("url") for item in groups if item.get("url")}
                if len(urls) == 1:
                    url = next(iter(urls))
                    title = (groups[0].get("title") if groups else "") or url
                    gaps.append(
                        Gap(
                            area="semantic_coverage",
                            gap_description=f"Only one competitor covers this embedded topic cluster ('{title}'); others lack it.",
                            suggested_angle="Own this topic cluster with a deep-dive angle before competitors expand",
                            difficulty=6,
                        )
                    )
                    suggestions.append(f"Own the cluster around: {title}")
        return CompetitorGap(competitors=competitors, gaps=gaps, suggestions=suggestions)

    @staticmethod
    def _token_overlap(a: str, b: str) -> float:
        tokens_a = set(a.lower().split())
        tokens_b = set(b.lower().split())
        if not tokens_a or not tokens_b:
            return 0.0
        return len(tokens_a & tokens_b) / len(tokens_a | tokens_b)
