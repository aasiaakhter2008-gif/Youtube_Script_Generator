import pytest

from app.agents.guardrails import GuardrailsAgent
from app.agents.insights import InsightsAgent
from app.agents.writer import WriterAgent
from app.pipeline.state import PipelineState
from app.schemas.script import (
    Channel,
    ChannelInsight,
    GuardrailsResult,
    Outline,
    OutlineSection,
    ScriptRequest,
    SectionType,
    VideoPerformance,
    WriterSection,
)
from app.services.billing import billing_service
from app.services.feedback import feedback_service
from app.services.prompt_registry import prompt_registry


class FakePhase4LLM:
    def __init__(self) -> None:
        self.last_prompt: str = ""
        self.insight_calls = 0

    async def structured(self, prompt, schema, **kwargs):
        self.last_prompt = prompt
        if schema is ChannelInsight:
            self.insight_calls += 1
            return ChannelInsight(channel_id="ch-1", video_id="vid-1", insight="Strong hook drove retention.", suggested_action="Use curiosity-first hooks.")
        if schema is GuardrailsResult:
            return GuardrailsResult(factual_risk=True, copyright_similarity=0.2, policy_flags=["medical_advice"], blocked=True)
        if schema is WriterSection:
            return WriterSection(section_type=SectionType.HOOK, title="Hook", content="You will not believe what happens during deep sleep.", b_roll_cues=["talking head"], on_screen_text=["Deep sleep"], word_count=10)
        raise ValueError(f"Unexpected schema: {schema}")


@pytest.mark.asyncio
async def test_insights_agent_builds_channel_insights() -> None:
    llm = FakePhase4LLM()
    agent = InsightsAgent(llm=llm)
    state = PipelineState(job_id="job-1", status="completed", insights=[])
    new_state = await agent.run(
        state,
        channel=Channel(id="ch-1", owner_user_id="user-1", youtube_channel_id="UC123", handle="@sleeplab", created_at=__import__("datetime").datetime.now(__import__("datetime").timezone.utc)),
        performances=[VideoPerformance(video_id="vid-1", script_job_id="job-1", views=1200, ctr=0.09, avg_view_duration_seconds=45.0, comments_count=7, fetched_at=__import__("datetime").datetime.now(__import__("datetime").timezone.utc))],
    )
    assert len(new_state.insights) == 1
    assert new_state.insights[0].video_id == "vid-1"
    assert new_state.insights[0].suggested_action


@pytest.mark.asyncio
async def test_guardrails_agent_blocks_risky_script() -> None:
    llm = FakePhase4LLM()
    agent = GuardrailsAgent(llm=llm)
    state = PipelineState(job_id="job-2", status="completed", sections=[WriterSection(section_type=SectionType.HOOK, title="Hook", content="Medical advice about sleep.", word_count=6)])
    new_state = await agent.run(state)
    assert new_state.guardrails is not None
    assert new_state.guardrails.blocked is True
    assert new_state.guardrails.factual_risk is True


@pytest.mark.asyncio
async def test_writer_prompt_includes_channel_insights() -> None:
    llm = FakePhase4LLM()
    agent = WriterAgent(llm=llm)
    state = PipelineState(
        job_id="job-3",
        status="completed",
        request=ScriptRequest(topic="The Science of Sleep", duration_minutes=8, format="long_form"),
        insights=[ChannelInsight(channel_id="ch-1", video_id="vid-1", insight="Strong hook drove retention.", suggested_action="Use curiosity-first hooks.")],
        outline=Outline(
            hook=OutlineSection(section_type=SectionType.HOOK, title="Hook", key_points=["k"], estimated_duration_seconds=20),
            intro=OutlineSection(section_type=SectionType.INTRO, title="Intro", key_points=["k"], estimated_duration_seconds=15),
            retention_loop=OutlineSection(section_type=SectionType.RETENTION_LOOP, title="Loop", key_points=["k"], estimated_duration_seconds=15),
            cta=OutlineSection(section_type=SectionType.CTA, title="CTA", key_points=["k"], estimated_duration_seconds=10),
            outro=OutlineSection(section_type=SectionType.OUTRO, title="Outro", key_points=["k"], estimated_duration_seconds=10),
        ),
    )
    await agent.run(state)
    assert "Channel insights" in llm.last_prompt
    assert "Strong hook drove retention" in llm.last_prompt


def test_prompt_registry_rollout_and_rollback() -> None:
    entry = prompt_registry.register(name="writer_v1", version=1, template="template-v1", rollout_pct=100)
    assert entry["active"] is True
    assert prompt_registry.get_active("writer_v1")["version"] == 1
    prompt_registry.register(name="writer_v1", version=2, template="template-v2", rollout_pct=0)
    assert prompt_registry.get_active("writer_v1")["version"] == 1
    rolled_back = prompt_registry.rollback(name="writer_v1", version=1)
    assert rolled_back is not None and rolled_back["active"] is True


def test_billing_plan_limits_and_credit_consumption() -> None:
    billing_service.consume(feature="generate", user_id="u-phase4-a", plan="free")
    billing_service.consume(feature="generate", user_id="u-phase4-a", plan="free")
    billing_service.consume(feature="generate", user_id="u-phase4-a", plan="free")
    billing_service.check_limit(feature="generate", user_id="u-phase4-a", plan="free")
    billing_service.consume(feature="generate", user_id="u-phase4-b", plan="pro")
    billing_service.check_limit(feature="competitor_gap", user_id="u-phase4-b", plan="pro")


@pytest.mark.asyncio
async def test_feedback_service_records_training_signal() -> None:
    record = await feedback_service.add_feedback(script_job_id="job-9", section_type="hook", rating="down", edited_content="Tighter hook text")
    assert record["rating"] == "down"
    records = await feedback_service.list_feedback("job-9")
    assert len(records) == 1
