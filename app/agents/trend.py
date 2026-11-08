from app.agents.base import BaseAgent
from app.pipeline.state import PipelineState
from app.schemas.trend import Trend, TrendList
from app.services.llm_client import BaseLLMClient


class TrendAgent(BaseAgent):
    """Ranks trending topics by relevance to the user's niche and voice."""

    name = "trend"

    def __init__(self, llm: BaseLLMClient = None) -> None:
        self.llm = llm

    async def run(self, state: PipelineState, **kwargs) -> PipelineState:
        niche = str(kwargs.get("niche") or "general")
        signals = list(kwargs.get("signals") or [])
        trends = self._heuristic_trends(niche, signals) if self.llm is None else await self._llm_rank(state, niche, signals)
        state.trends = trends
        return state

    async def _llm_rank(self, state: PipelineState, niche: str, signals: list) -> list:
        prompt = (
            "You are the Trend Agent. Given niche trends signals, rank the topics by relevance to the niche "
            f"'{niche}' and return trending topics with a short 'why' reason.\n\nSignals: "
            f"{[s.get('keyword') if isinstance(s, dict) else str(s) for s in signals]}\n\n"
            "Respond with JSON: {\"trends\": [{\"keyword\": \"...\", \"score\": 0-100, \"reason\": \"...\", \"source\": \"...\"}]}"
        )
        result = await self.llm.structured(prompt, TrendList, tool_name="trend_list")
        return list(result.trends) if result is not None and getattr(result, "trends", None) else []

    def _heuristic_trends(self, niche: str, signals: list) -> list:
        keywords = [str(s.get("keyword") if isinstance(s, dict) else s) for s in signals]
        scored = []
        for keyword in keywords:
            overlap = len(set(keyword.lower().split()) & set(niche.lower().split()))
            scored.append(Trend(keyword=keyword, score=float(min(95, 30 + overlap * 20)), reason="Matches niche interest", source="heuristic"))
        if not scored:
            scored = [Trend(keyword=niche.title(), score=50.0, reason="Niche default", source="heuristic")]
        return scored
