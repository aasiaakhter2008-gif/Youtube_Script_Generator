from typing import Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from app.schemas.competitor import CompetitorGap
from app.services.competitors import competitor_service


class CompetitorGapRequest(BaseModel):
    urls: list[str] = Field(min_length=1, max_length=5)
    user_id: Optional[str] = None
    workspace_id: Optional[str] = None


router = APIRouter(prefix="/competitors", tags=["competitors"])


@router.post("/gap", response_model=CompetitorGap)
async def competitor_gap(request: CompetitorGapRequest) -> CompetitorGap:
    gap = await competitor_service.analyze(
        request.urls,
        user_id=request.user_id or "global",
        workspace_id=request.workspace_id or "default",
    )
    if gap is None:
        raise HTTPException(status_code=500, detail="Competitor gap analysis failed")
    return gap
