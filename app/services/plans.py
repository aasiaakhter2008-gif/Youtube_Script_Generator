from typing import Optional
from uuid import uuid4

from app.schemas.plan import SeriesPlan


class PlanStore:
    """In-memory plan registry (Phase 3 MVP; move to PostgreSQL later)."""

    def __init__(self) -> None:
        self._plans: dict[str, SeriesPlan] = {}

    async def save(self, plan: SeriesPlan) -> SeriesPlan:
        if not plan.id:
            plan.id = str(uuid4())
        self._plans[plan.id] = plan
        return plan

    async def get(self, plan_id: str) -> Optional[SeriesPlan]:
        return self._plans.get(plan_id)

    async def delete(self, plan_id: str) -> None:
        self._plans.pop(plan_id, None)


plan_store = PlanStore()
