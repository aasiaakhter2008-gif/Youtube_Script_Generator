from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from app.agents.translator import TranslationAgent
from app.core.config import settings
from app.core.security import verify_api_key
from app.schemas.script import DubScript
from app.services.generation import job_pipeline_state
from app.services.llm_client import get_llm_client

router = APIRouter(prefix="/scripts", tags=["dub"], dependencies=[Depends(verify_api_key)])


class DubRequest(BaseModel):
    language: str = "Urdu"


@router.post("/{job_id}/dub", response_model=DubScript)
async def dub_script(job_id: str, body: DubRequest) -> DubScript:
    """Translate the job's final script into a target language (dubbing-ready output)."""
    state = await job_pipeline_state(job_id)
    if state is None:
        raise HTTPException(status_code=404, detail="Script job not found")
    supported = [lang.strip() for lang in settings.SUPPORTED_LANGUAGES.split(",") if lang.strip()]
    if body.language not in supported:
        raise HTTPException(status_code=400, detail=f"Unsupported language {body.language}. Supported: {supported}")
    translator = TranslationAgent(llm=get_llm_client(role="writer"))
    new_state = await translator.run(state, target_language=body.language)
    dub = new_state.dub_script
    if dub is None:
        raise HTTPException(status_code=500, detail="Translation failed to produce a dub script")
    return dub
