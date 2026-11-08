from typing import Optional

from app.schemas.script import HookTestPlan, HookTestResult


class HookTestStore:
    """In-memory hook A/B test plan + results log (Phase 3 item 4; move to Redis/DB later)."""

    def __init__(self) -> None:
        self._plans: dict[str, HookTestPlan] = {}
        self._results: dict[str, HookTestResult] = {}

    async def save_plan(self, plan: HookTestPlan) -> HookTestPlan:
        self._plans[plan.job_id] = plan
        return plan

    async def get_plan(self, job_id: str) -> Optional[HookTestPlan]:
        return self._plans.get(job_id)

    async def save_result(self, result: HookTestResult) -> HookTestResult:
        self._results[result.job_id] = result
        return result

    async def get_result(self, job_id: str) -> Optional[HookTestResult]:
        return self._results.get(job_id)

    async def delete_plan(self, job_id: str) -> None:
        self._plans.pop(job_id, None)
        self._results.pop(job_id, None)


hook_test_store = HookTestStore()
