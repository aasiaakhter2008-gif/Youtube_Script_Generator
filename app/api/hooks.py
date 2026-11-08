from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from app.api.scripts import pipeline
from app.core.security import verify_api_key
from app.schemas.script import HookTestPlan, HookTestResult
from app.services.generation import job_pipeline_state
from app.services.hook_tests import hook_test_store

router = APIRouter(prefix="/scripts", tags=["hooks"], dependencies=[Depends(verify_api_key)])


class HookTestResultCreate(BaseModel):
    winner_hook: str = ""
    metrics: dict = {}
    notes: str = ""


@router.post("/{job_id}/hook-tests", response_model=HookTestPlan)
async def generate_hook_tests(job_id: str) -> HookTestPlan:
    state = await job_pipeline_state(job_id)
    if state is None:
        raise HTTPException(status_code=404, detail="Script job not found")
    try:
        new_state = await pipeline.hook_agent.run(state, mode="tests")
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=503, detail="Hook-test agent temporarily unavailable (LLM overloaded). Please try again shortly.") from exc
    plan = new_state.hook_test
    if plan is None:
        raise HTTPException(status_code=500, detail="Hook test plan generation failed")
    await hook_test_store.save_plan(plan)
    return plan


@router.post("/{job_id}/hook-tests/results")
async def log_hook_test_result(job_id: str, result: HookTestResultCreate) -> HookTestResult:
    stored = await hook_test_store.save_result(HookTestResult(job_id=job_id, winner_hook=result.winner_hook, metrics=result.metrics, notes=result.notes))
    return stored


@router.get("/{job_id}/hook-tests/results")
async def get_hook_test_result(job_id: str) -> HookTestResult:
    result = await hook_test_store.get_result(job_id)
    if result is None:
        raise HTTPException(status_code=404, detail="No hook test result recorded for this job")
    return result
