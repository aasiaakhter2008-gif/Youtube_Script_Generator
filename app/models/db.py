from datetime import datetime, timezone
from typing import Optional
from uuid import uuid4

from sqlalchemy import JSON, Column, DateTime
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlmodel import Field, SQLModel

from app.core.config import settings

engine = create_async_engine(settings.DATABASE_URL, echo=False, pool_pre_ping=True)
async_session = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)


def utcnow() -> datetime:
    """Timezone-aware UTC timestamp (SQLModel stores UTC and returns it aware)."""
    return datetime.now(timezone.utc)


class ScriptJob(SQLModel, table=True):
    """Persisted generation job. JSON blob columns hold outline/final_script/critique/payload."""

    id: str = Field(default_factory=lambda: str(uuid4()), primary_key=True)
    topic: str = Field(index=True)
    status: str = Field(default="pending", index=True)
    owner: str = Field(default="global", index=True)
    payload: Optional[dict] = Field(default=None, sa_column=Column(JSON, nullable=True))
    final_script: Optional[dict] = Field(default=None, sa_column=Column(JSON, nullable=True))
    outline: Optional[dict] = Field(default=None, sa_column=Column(JSON, nullable=True))
    critique: Optional[dict] = Field(default=None, sa_column=Column(JSON, nullable=True))
    error: Optional[str] = None
    created_at: datetime = Field(default_factory=utcnow, sa_column=DateTime)
    updated_at: datetime = Field(default_factory=utcnow, sa_column=DateTime)


class Workspace(SQLModel, table=True):
    """Phase 4 collaboration: team workspace."""

    id: str = Field(default_factory=lambda: str(uuid4()), primary_key=True)
    name: str = Field(index=True)
    owner_id: str = Field(index=True)
    created_at: datetime = Field(default_factory=utcnow, sa_column=DateTime)


class WorkspaceMember(SQLModel, table=True):
    """Phase 4 collaboration: workspace member with role (owner | editor | viewer)."""

    id: str = Field(default_factory=lambda: str(uuid4()), primary_key=True)
    workspace_id: str = Field(index=True)
    user_id: str = Field(index=True)
    role: str = Field(default="viewer")
    joined_at: datetime = Field(default_factory=utcnow, sa_column=DateTime)


class ScriptComment(SQLModel, table=True):
    """Phase 4 collaboration: comment on a script section."""

    id: str = Field(default_factory=lambda: str(uuid4()), primary_key=True)
    script_job_id: str = Field(index=True)
    section_type: str = ""
    content: str = Field()
    created_by: str = ""
    created_at: datetime = Field(default_factory=utcnow, sa_column=DateTime)


class ScriptActivity(SQLModel, table=True):
    """Phase 4 collaboration: per-script activity/audit log."""

    id: str = Field(default_factory=lambda: str(uuid4()), primary_key=True)
    script_job_id: str = Field(index=True)
    actor: str = ""
    action: str = ""
    details: Optional[dict] = Field(default=None, sa_column=Column(JSON, nullable=True))
    created_at: datetime = Field(default_factory=utcnow, sa_column=DateTime)


class Channel(SQLModel, table=True):
    """Phase 4/3: connected YouTube channel for performance feedback."""

    id: str = Field(default_factory=lambda: str(uuid4()), primary_key=True)
    owner_user_id: str = Field(index=True)
    youtube_channel_id: str = Field(index=True)
    handle: str = ""
    created_at: datetime = Field(default_factory=utcnow, sa_column=DateTime)


class VideoPerformance(SQLModel, table=True):
    """Phase 4: published video stats linked to a generated script job."""

    id: str = Field(default_factory=lambda: str(uuid4()), primary_key=True)
    video_id: str = Field(index=True)
    script_job_id: str = Field(default="")
    views: int = Field(default=0)
    ctr: float = Field(default=0.0)
    avg_view_duration_seconds: float = Field(default=0.0)
    comments_count: int = Field(default=0)
    fetched_at: datetime = Field(default_factory=utcnow, sa_column=DateTime)


class VoiceProfile(SQLModel, table=True):
    """Voice/style profile: writing samples embedded for retrieval by the writer agent."""

    id: str = Field(default_factory=lambda: str(uuid4()), primary_key=True)
    name: str = Field(index=True)
    user_id: str = Field(default="global", index=True)
    workspace_id: str = Field(default="default", index=True)
    source: str = "user"
    created_at: datetime = Field(default_factory=utcnow, sa_column=DateTime)
