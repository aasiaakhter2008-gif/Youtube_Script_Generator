from typing import List, Optional

from pydantic import BaseModel, Field

from app.schemas.competitor import CompetitorGap
from app.schemas.plan import SeriesPlan
from app.schemas.script import ChosenHook, CriticResult, ChannelInsight, DubScript, GuardrailsResult, HookTestPlan, Outline, ScriptRequest, Storyboard, WriterSection
from app.schemas.trend import Trend


class PipelineState(BaseModel):
    """Shared state passed between agents in the plain-async pipeline."""

    job_id: str = ""
    request: Optional[ScriptRequest] = None
    outline: Optional[Outline] = None
    hooks: Optional[ChosenHook] = None
    sections: List[WriterSection] = Field(default_factory=list)
    critic_feedback: Optional[CriticResult] = None
    revision_count: int = 0
    status: str = "pending"  # pending | running | completed | failed
    plan: Optional[SeriesPlan] = None
    trends: List[Trend] = Field(default_factory=list)
    gap_analysis: Optional[CompetitorGap] = None
    hook_test: Optional[HookTestPlan] = None
    dub_script: Optional[DubScript] = None
    storyboard: Optional[Storyboard] = None
    insights: List[ChannelInsight] = Field(default_factory=list)
    guardrails: Optional[GuardrailsResult] = None
