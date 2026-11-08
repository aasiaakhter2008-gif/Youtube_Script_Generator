from pydantic import BaseModel, Field


class CompetitorVideo(BaseModel):
    url: str
    title: str = ""
    channel: str = ""


class Gap(BaseModel):
    area: str
    gap_description: str
    suggested_angle: str
    difficulty: int = Field(ge=1, le=10)


class CompetitorGap(BaseModel):
    competitors: list[str] = Field(default_factory=list)
    gaps: list[Gap] = Field(default_factory=list)
    suggestions: list[str] = Field(default_factory=list)


class GapAnalysis(BaseModel):
    gaps: list[Gap] = Field(default_factory=list)
    suggestions: list[str] = Field(default_factory=list)
