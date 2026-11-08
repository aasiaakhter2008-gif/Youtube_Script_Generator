from typing import Optional

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field

from app.core.security import verify_api_key
from app.services.feedback import feedback_service

router = APIRouter(prefix="/feedback", tags=["feedback"], dependencies=[Depends(verify_api_key)])


class FeedbackCreate(BaseModel):
    script_job_id: str = Field(min_length=1, max_length=200)
    section_type: str = Field(default="hook", max_length=50)
    rating: str = Field(pattern="^(up|down)$")
    edited_content: Optional[str] = Field(default=None, max_length=20000)


@router.post("", status_code=201)
async def add_feedback(body: FeedbackCreate) -> dict:
    return await feedback_service.add_feedback(
        script_job_id=body.script_job_id,
        section_type=body.section_type,
        rating=body.rating,
        edited_content=body.edited_content,
    )


@router.get("/{script_job_id}")
async def list_feedback(script_job_id: str) -> list[dict]:
    return await feedback_service.list_feedback(script_job_id)
