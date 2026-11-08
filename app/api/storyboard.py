from fastapi import APIRouter, Depends, HTTPException, Query, Response
from fastapi.responses import JSONResponse

from app.agents.storyboard import StoryboardAgent
from app.core.security import verify_api_key
from app.schemas.script import Storyboard
from app.services.export import export_storyboard
from app.services.generation import job_pipeline_state
from app.services.llm_client import get_llm_client
from app.services.storyboards import storyboard_store

router = APIRouter(prefix="/scripts", tags=["storyboard"], dependencies=[Depends(verify_api_key)])


@router.post("/{job_id}/storyboard", response_model=Storyboard)
async def create_storyboard(job_id: str) -> Storyboard:
    state = await job_pipeline_state(job_id)
    if state is None:
        raise HTTPException(status_code=404, detail="Script job not found")
    agent = StoryboardAgent(llm=get_llm_client(role="writer"))
    try:
        new_state = await agent.run(state)
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=503, detail="Storyboard agent temporarily unavailable (LLM overloaded). Please try again shortly.") from exc
    storyboard = new_state.storyboard
    if storyboard is None:
        raise HTTPException(status_code=500, detail="Storyboard generation failed")
    await storyboard_store.save(storyboard)
    return storyboard


@router.get("/{job_id}/storyboard", response_model=Storyboard)
async def get_storyboard(job_id: str) -> Storyboard:
    storyboard = await storyboard_store.get(job_id)
    if storyboard is None:
        raise HTTPException(status_code=404, detail="Storyboard not found. Generate one first via POST /scripts/{job_id}/storyboard")
    return storyboard


@router.get("/{job_id}/storyboard/export")
async def export_storyboard_endpoint(job_id: str, format: str = Query("json", description="Export format: csv | pdf")) -> Response:
    storyboard = await storyboard_store.get(job_id)
    if storyboard is None:
        raise HTTPException(status_code=404, detail="Storyboard not found. Generate one first via POST /scripts/{job_id}/storyboard")
    if format == "json":
        return JSONResponse(content=storyboard.model_dump())
    file_bytes, media_type = export_storyboard(storyboard, format)
    return Response(content=file_bytes, media_type=media_type, headers={"Content-Disposition": f'attachment; filename="storyboard_{job_id}.{format}"'})
