from fastapi import APIRouter, BackgroundTasks, HTTPException
from pydantic import BaseModel, Field

from app.agents.planner import PlannerAgent
from app.pipeline.state import PipelineState
from app.schemas.plan import PlanItemUpdate, SeriesPlan
from app.schemas.script import JobAccepted, ScriptRequest
from app.services.generation import run_generation_job
from app.services.jobs import job_store
from app.services.llm_client import get_llm_client
from app.api.scripts import pipeline
from app.services.plans import plan_store

planner = PlannerAgent(llm=get_llm_client(role="outline"))

router = APIRouter(prefix="/plans", tags=["plans"])


class PlanCreate(BaseModel):
    niche: str = Field(min_length=2, max_length=200)
    goal: str = Field(default="", max_length=500)
    episodes: int = Field(default=4, ge=1, le=12)


@router.post("", response_model=SeriesPlan)
async def create_plan(body: PlanCreate) -> SeriesPlan:
    try:
        state = await planner.run(PipelineState(job_id="plan", status="running"), niche=body.niche, goal=body.goal, episodes=body.episodes)
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=503, detail="Planner temporarily unavailable (LLM overloaded). Please try again shortly.") from exc
    plan = state.plan
    if plan is None:
        raise HTTPException(status_code=500, detail="Planner failed to produce a plan")
    saved = await plan_store.save(plan)
    return saved


@router.get("/{plan_id}", response_model=SeriesPlan)
async def get_plan(plan_id: str) -> SeriesPlan:
    plan = await plan_store.get(plan_id)
    if plan is None:
        raise HTTPException(status_code=404, detail="Plan not found")
    return plan


@router.patch("/{plan_id}/items/{item_id}", response_model=SeriesPlan)
async def patch_plan_item(plan_id: str, item_id: str, item: PlanItemUpdate) -> SeriesPlan:
    plan = await plan_store.get(plan_id)
    if plan is None:
        raise HTTPException(status_code=404, detail="Plan not found")
    found = False
    for ep in plan.episodes:
        if ep.id == item_id:
            if item.title is not None:
                ep.title = item.title
            if item.angle is not None:
                ep.angle = item.angle
            if item.target_keyword is not None:
                ep.target_keyword = item.target_keyword
            if item.format is not None:
                ep.format = item.format
            if item.publish_date is not None:
                ep.publish_date = item.publish_date
            if item.estimated_duration_minutes is not None:
                ep.estimated_duration_minutes = item.estimated_duration_minutes
            if item.notes is not None:
                ep.notes = item.notes
            found = True
            break
    if not found:
        raise HTTPException(status_code=404, detail="Plan item not found")
    return plan


@router.post("/{plan_id}/items/{item_id}/generate-script", response_model= JobAccepted)
async def generate_script_from_item(
    plan_id: str,
    item_id: str,
    background_tasks: BackgroundTasks,
) -> JobAccepted:
    plan = await plan_store.get(plan_id)
    if plan is None:
        raise HTTPException(status_code=404, detail="Plan not found")
    item = next((e for e in plan.episodes if e.id == item_id), None)
    if item is None:
        raise HTTPException(status_code=404, detail="Plan item not found")
    request = ScriptRequest(
        topic=item.title,
        audience="General audience",
        tone="educational",
        language="English",
        duration_minutes=item.estimated_duration_minutes,
        format=item.format or "long_form",
    )
    job = await job_store.create(topic=request.topic, request=request)
    background_tasks.add_task(run_generation_job, job.id, pipeline)
    return JobAccepted(job_id=job.id, status=job.status)
