from fastapi import APIRouter, Query

from app.schemas.trend import Trend
from app.services.trends import trend_service

router = APIRouter(prefix="/trends", tags=["trends"])


@router.get("", response_model=list[Trend])
async def get_trends(niche: str = Query("technology")) -> list:
    return await trend_service.get_trends(niche)


@router.post("/refresh", response_model=list[Trend])
async def refresh_trends(niche: str = Query("technology")) -> list:
    trend_service.clear_cache(niche)
    return await trend_service.get_trends(niche)
