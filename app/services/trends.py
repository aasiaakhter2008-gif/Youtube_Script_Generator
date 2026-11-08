from typing import Optional

from app.agents.trend import TrendAgent
from app.pipeline.state import PipelineState
from app.schemas.trend import Trend


class TrendService:
    """Caches trend rankings per niche (Redis in prod, in-memory fallback)."""

    def __init__(self, agent: TrendAgent) -> None:
        self.agent = agent
        self._cache: dict[str, list[Trend]] = {}

    async def get_trends(self, niche: str, *, use_cache: bool = True) -> list:
        key = niche.strip().lower()
        if use_cache:
            cached = self._cache.get(key)
            if cached is not None:
                return list(cached)
        state = await self.agent.run(PipelineState(job_id="trend", status="running"), niche=niche)
        trends = list(state.trends)
        if use_cache:
            self._cache[key] = list(trends)
        return trends

    def clear_cache(self, niche: Optional[str] = None) -> None:
        if niche is None:
            self._cache.clear()
        else:
            self._cache.pop(niche.strip().lower(), None)


trend_service = TrendService(TrendAgent())
