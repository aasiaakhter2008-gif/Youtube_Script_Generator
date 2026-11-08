from typing import Optional

from pydantic import BaseModel, Field


class VoiceProfileCreate(BaseModel):
    name: str = Field(min_length=2, max_length=200)
    texts: list[str] = Field(min_length=1, max_length=50)
    user_id: Optional[str] = None
    workspace_id: Optional[str] = None


class VoiceProfileRead(BaseModel):
    id: str
    name: str
    user_id: str
    workspace_id: str
    source: str
    chunk_count: int
    created_at: Optional[str] = None


class VoiceProfileSearchRequest(BaseModel):
    query: str = Field(min_length=3, max_length=2000)
    voice_profile_id: Optional[str] = None
    top_k: int = Field(default=5, ge=1, le=20)


class VoiceProfileSearchResult(BaseModel):
    id: str
    text: str
    score: float
    metadata: dict = {}
