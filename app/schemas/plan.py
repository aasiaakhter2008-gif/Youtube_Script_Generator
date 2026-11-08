from typing import Optional

from pydantic import BaseModel, Field


class PlanItem(BaseModel):
    id: str = ""
    title: str = Field(min_length=3, max_length=300)
    angle: str = Field(default="", max_length=500)
    target_keyword: str = Field(default="", max_length=200)
    format: str = "long_form"
    publish_date: str = Field(default="2026-11-01")
    estimated_duration_minutes: int = Field(default=8, ge=1, le=30)
    notes: str = ""


class PlanItemUpdate(BaseModel):
    title: Optional[str] = None
    angle: Optional[str] = None
    target_keyword: Optional[str] = None
    format: Optional[str] = None
    publish_date: Optional[str] = None
    estimated_duration_minutes: Optional[int] = None
    notes: Optional[str] = None


class SeriesPlan(BaseModel):
    id: str = ""
    niche: str = Field(min_length=2, max_length=200)
    goal: str = Field(default="", max_length=500)
    series_title: str = Field(min_length=2, max_length=300)
    episodes: list[PlanItem] = Field(default_factory=list)
