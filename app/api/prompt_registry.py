
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from app.core.security import verify_api_key
from app.services.prompt_registry import prompt_registry

router = APIRouter(prefix="/prompts", tags=["prompts"], dependencies=[Depends(verify_api_key)])


class PromptRegister(BaseModel):
    name: str = Field(min_length=2, max_length=100)
    version: int = Field(ge=1, le=100)
    template: str = Field(min_length=10, max_length=20000)
    rollout_pct: int = Field(default=100, ge=0, le=100)


@router.post("", status_code=201)
async def register_prompt(body: PromptRegister) -> dict:
    return prompt_registry.register(name=body.name, version=body.version, template=body.template, rollout_pct=body.rollout_pct)


@router.get("/{name}")
async def get_active_prompt(name: str) -> dict:
    prompt = prompt_registry.get_active(name)
    if prompt is None:
        raise HTTPException(status_code=404, detail="Prompt not found")
    return prompt


@router.post("/{name}/rollback")
async def rollback_prompt(name: str, version: int = 1) -> dict:
    prompt = prompt_registry.rollback(name, version)
    if prompt is None:
        raise HTTPException(status_code=404, detail="Prompt version not found")
    return prompt
