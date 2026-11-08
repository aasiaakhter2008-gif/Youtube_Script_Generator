from datetime import datetime
from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field


class Tone(str, Enum):
    EDUCATIONAL = "educational"
    FUNNY = "funny"
    STORYTELLING = "storytelling"
    MOTIVATIONAL = "motivational"


class ScriptLanguage(str, Enum):
    ENGLISH = "English"
    URDU = "Urdu"
    ROMAN_URDU = "Roman Urdu"
    HINDI = "Hindi"


class ScriptFormat(str, Enum):
    LONG_FORM = "long_form"
    SHORTS = "shorts"


class SectionType(str, Enum):
    HOOK = "hook"
    INTRO = "intro"
    MAIN_POINT = "main_point"
    RETENTION_LOOP = "retention_loop"
    CTA = "cta"
    OUTRO = "outro"


class ScriptStatus(str, Enum):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    DRAFT = "draft"
    REVIEW = "review"
    APPROVED = "approved"
    PUBLISHED = "published"


class ScriptRequest(BaseModel):
    topic: str = Field(min_length=3, max_length=300)
    audience: str = Field(default="General audience", max_length=200)
    tone: Tone = Tone.EDUCATIONAL
    language: ScriptLanguage = ScriptLanguage.ENGLISH
    duration_minutes: int = Field(ge=1, le=30)
    format: ScriptFormat = ScriptFormat.LONG_FORM
    voice_profile_id: Optional[str] = None
    user_id: Optional[str] = None
    workspace_id: Optional[str] = None


class OutlineSection(BaseModel):
    section_type: SectionType
    title: str = Field(min_length=1, max_length=200)
    key_points: list[str] = Field(default_factory=list)
    estimated_duration_seconds: int = Field(default=0, ge=0, le=3600)


class Outline(BaseModel):
    hook: OutlineSection
    intro: OutlineSection
    main_points: list[OutlineSection] = Field(default_factory=list)
    retention_loop: OutlineSection
    cta: OutlineSection
    outro: OutlineSection


class HookVariation(BaseModel):
    text: str = Field(min_length=1, max_length=500)
    style: str = Field(default="question")


class ChosenHook(BaseModel):
    text: str = Field(min_length=1, max_length=500)
    variations: list[HookVariation] = Field(default_factory=list)


class WriterSection(BaseModel):
    section_type: SectionType
    title: str = Field(min_length=1, max_length=200)
    content: str = Field(min_length=1)
    b_roll_cues: list[str] = Field(default_factory=list)
    on_screen_text: list[str] = Field(default_factory=list)
    word_count: int = 0


class WrittenScript(BaseModel):
    sections: list[WriterSection] = Field(default_factory=list)
    word_count: int = 0


class CriticAssessment(BaseModel):
    hook_strength: float = Field(ge=0, le=10)
    pacing: float = Field(ge=0, le=10)
    clarity: float = Field(ge=0, le=10)
    repetition: float = Field(ge=0, le=10)
    feedback: str = ""
    passed: bool = False


class CriticResult(BaseModel):
    assessment: CriticAssessment
    weak_sections: list[str] = Field(default_factory=list)


class ScriptJobRead(BaseModel):
    id: str
    status: ScriptStatus
    topic: str
    audience: str
    tone: Tone
    language: ScriptLanguage
    duration_minutes: int
    format: ScriptFormat
    outline: Optional[Outline] = None
    final_script: Optional[WrittenScript] = None
    critique: Optional[CriticResult] = None
    error: Optional[str] = None
    # Which actual model served each role ({"writer": "...", "critic": "...", ...})
    model_usage: dict[str, str] = Field(default_factory=dict)
    created_at: datetime
    updated_at: datetime


class ScriptSummary(BaseModel):
    id: str
    topic: str
    status: ScriptStatus
    format: ScriptFormat
    duration_minutes: int
    created_at: datetime


class RegenerateSectionRequest(BaseModel):
    section_type: SectionType
    instruction: Optional[str] = Field(default=None, max_length=1000)


class JobAccepted(BaseModel):
    job_id: str
    status: str = "pending"


class HookScore(BaseModel):
    """Standalone critic score for a single hook variant (A/B testing)."""

    hook_strength: float = Field(ge=0, le=10)
    reasoning: str = ""


class HookVariant(BaseModel):
    text: str = Field(min_length=1, max_length=500)
    style: str = "curiosity"
    angle: str = "curiosity"  # curiosity | shock | story | question | bold_claim


class HookVariantList(BaseModel):
    variants: list[HookVariant] = Field(default_factory=list)


class HookEvaluation(BaseModel):
    hook_index: int = 0
    hook_strength: float = Field(ge=0, le=10)
    reasoning: str = ""


class HookTestPlan(BaseModel):
    job_id: str = ""
    baseline_hook: str = ""
    candidates: list[HookVariant] = Field(default_factory=list)
    evaluations: list[HookEvaluation] = Field(default_factory=list)
    metrics: list[str] = Field(default_factory=lambda: ["first_30_sec_retention", "ctr"])
    winner: Optional[str] = None


class HookTestResult(BaseModel):
    job_id: str = ""
    winner_hook: str = ""
    metrics: dict = {}
    notes: str = ""


class TranslatedSection(BaseModel):
    source_section_type: str = ""
    translated_content: str = Field(min_length=1)
    duration_seconds: float = 0.0


class DubScript(BaseModel):
    language: str = "Urdu"
    source_language: str = "English"
    sections: list[TranslatedSection] = Field(default_factory=list)
    notes: str = ""


class Shot(BaseModel):
    section_type: str = ""
    shot_type: str = "talking_head"
    visual_description: str = ""
    b_roll_keywords: list[str] = Field(default_factory=list)
    on_screen_text: str = ""
    estimated_duration_seconds: float = 0.0


class Storyboard(BaseModel):
    job_id: str = ""
    shots: list[Shot] = Field(default_factory=list)


class Channel(BaseModel):
    id: str = ""
    owner_user_id: str = ""
    youtube_channel_id: str = ""
    handle: str = ""
    created_at: datetime


class VideoPerformance(BaseModel):
    video_id: str = ""
    script_job_id: str = ""
    views: int = 0
    ctr: float = 0.0
    avg_view_duration_seconds: float = 0.0
    comments_count: int = 0
    fetched_at: datetime


class ChannelInsight(BaseModel):
    channel_id: str = ""
    video_id: str = ""
    insight: str = ""
    suggested_action: str = ""


class GuardrailsResult(BaseModel):
    factual_risk: bool = False
    copyright_similarity: float = 0.0
    policy_flags: list[str] = Field(default_factory=list)
    blocked: bool = False


class Workspace(BaseModel):
    id: str = ""
    name: str = Field(min_length=2, max_length=200)
    owner_id: str = ""
    created_at: datetime


class WorkspaceMember(BaseModel):
    id: str = ""
    workspace_id: str = ""
    user_id: str = ""
    role: str = "viewer"  # owner | editor | viewer


class ScriptComment(BaseModel):
    id: str = ""
    script_job_id: str = ""
    section_type: str = ""
    content: str = Field(min_length=1, max_length=5000)
    created_by: str = ""
    created_at: datetime


class ScriptActivity(BaseModel):
    id: str = ""
    script_job_id: str = ""
    actor: str = ""
    action: str = ""
    details: Optional[dict] = {}
    created_at: datetime
