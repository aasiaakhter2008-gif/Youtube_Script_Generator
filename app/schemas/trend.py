from pydantic import BaseModel, Field


class Trend(BaseModel):
    keyword: str = Field(min_length=2, max_length=200)
    score: float = Field(ge=0, le=100)
    reason: str = ""
    source: str = "youtube"


class TrendList(BaseModel):
    trends: list[Trend] = Field(default_factory=list)
