import asyncio

import pytest

from app.agents.critic import CriticAgent
from app.agents.gap import CompetitorGapAgent
from app.agents.hook import HookAgent
from app.agents.outline import OutlineAgent
from app.agents.planner import PlannerAgent
from app.agents.trend import TrendAgent
from app.agents.writer import WriterAgent
from app.pipeline.events import EventBus
from app.pipeline.runner import Pipeline
from app.pipeline.state import PipelineState
from app.schemas.competitor import CompetitorVideo
from app.schemas.plan import SeriesPlan
from app.schemas.script import (
    ChosenHook,
    CriticAssessment,
    CriticResult,
    Outline,
    OutlineSection,
    ScriptRequest,
    SectionType,
    WriterSection,
)
from app.schemas.trend import Trend
from app.services.llm_client import BaseLLMClient


def _outline() -> Outline:
    return Outline(
        hook=OutlineSection(section_type=SectionType.HOOK, title="The science of sleep", key_points=[], estimated_duration_seconds=20),
        intro=OutlineSection(section_type=SectionType.INTRO, title="Why it matters", key_points=["sleep"], estimated_duration_seconds=30),
        main_points=[
            OutlineSection(section_type=SectionType.MAIN_POINT, title="Circadian rhythm", key_points=["rhythm"], estimated_duration_seconds=120),
        ],
        retention_loop=OutlineSection(section_type=SectionType.RETENTION_LOOP, title="Common mistakes", key_points=[], estimated_duration_seconds=30),
        cta=OutlineSection(section_type=SectionType.CTA, title="Subscribe", key_points=[], estimated_duration_seconds=15),
        outro=OutlineSection(section_type=SectionType.OUTRO, title="Wrap up", key_points=[], estimated_duration_seconds=15),
    )


def _critique(passed: bool, weak=None) -> CriticResult:
    return CriticResult(
        assessment=CriticAssessment(
            hook_strength=8.0 if passed else 4.0,
            pacing=8.0 if passed else 5.0,
            clarity=8.0 if passed else 6.0,
            repetition=8.0 if passed else 7.0,
            feedback="Solid" if passed else "Needs work",
            passed=passed,
        ),
        weak_sections=weak or [],
    )


class FakeLLMClient(BaseLLMClient):
    def __init__(self, critic_results=None) -> None:
        self.critic_results = list(critic_results or [_critique(passed=True)])
        self.critic_calls = 0
        self.writer_calls = 0

    async def structured(self, prompt, schema, **kwargs):
        if schema is Outline:
            return _outline()
        if schema is ChosenHook:
            return ChosenHook(text="Did you know your brain cleans itself while you sleep?", variations=[])
        if schema is WriterSection:
            self.writer_calls += 1
            return WriterSection(
                section_type=SectionType.HOOK,
                title="Hook",
                content="You will not believe what happens during deep sleep.",
                b_roll_cues=["talking head", "b-roll of sleeping"],
                on_screen_text=["Deep sleep"],
                word_count=10,
            )
        if schema is CriticResult:
            result = self.critic_results[min(self.critic_calls, len(self.critic_results) - 1)]
            self.critic_calls += 1
            return result
        if schema is SeriesPlan:
            return SeriesPlan(
                id="",
                niche="sleep science",
                goal="grow audience",
                series_title="The Science of Sleep",
                episodes=[],
            )
        raise ValueError(f"Unexpected schema: {schema}")


@pytest.mark.asyncio
async def test_outline_agent_returns_validated_outline(sample_request) -> None:
    agent = OutlineAgent(llm=FakeLLMClient())
    state = PipelineState(job_id="job-1", request=sample_request, status="running")
    new_state = await agent.run(state)
    assert isinstance(new_state.outline, Outline)
    assert new_state.outline.hook.title == "The science of sleep"


@pytest.mark.asyncio
async def test_writer_agent_writes_sections_with_cues(sample_request) -> None:
    agent = WriterAgent(llm=FakeLLMClient())
    state = PipelineState(job_id="job-1", request=sample_request, status="running", outline=_outline())
    new_state = await agent.run(state)
    assert len(new_state.sections) == 6
    assert all(isinstance(s, WriterSection) for s in new_state.sections)
    assert new_state.sections[0].b_roll_cues
    assert new_state.sections[0].on_screen_text


@pytest.mark.asyncio
async def test_critic_agent_sets_feedback_and_passed_flag() -> None:
    agent = CriticAgent(llm=FakeLLMClient(critic_results=[_critique(passed=False, weak=["hook"])]), pass_threshold=8.0)
    state = PipelineState(job_id="job-1", status="running", request=ScriptRequest(topic="The Science of Sleep", audience="College students", duration_minutes=8))
    new_state = await agent.run(state)
    assert new_state.critic_feedback is not None
    assert new_state.critic_feedback.assessment.passed is False
    assert new_state.critic_feedback.weak_sections == ["hook"]


@pytest.mark.asyncio
async def test_pipeline_completes_and_emits_events(sample_request) -> None:
    llm = FakeLLMClient(critic_results=[_critique(passed=True)])
    bus = EventBus()
    pipeline = Pipeline(
        outline_agent=OutlineAgent(llm=llm),
        hook_agent=HookAgent(llm=llm),
        writer_agent=WriterAgent(llm=llm),
        critic_agent=CriticAgent(llm=llm, pass_threshold=8.0),
        event_bus=bus,
        max_revisions=2,
        pass_threshold=8.0,
    )
    events: list = []

    async def collect() -> None:
        async for event in bus.subscribe("job-1"):
            events.append(event)
            if event.event in ("completed", "failed"):
                break

    task = asyncio.create_task(collect())
    state = await pipeline.run("job-1", sample_request)
    await task

    assert state.status == "completed"
    assert any(e.event == "agent.started" and e.agent == "outline" for e in events)
    assert any(e.event == "agent.completed" and e.agent == "outline" for e in events)
    assert any(e.event == "hook.selected" for e in events)
    assert any(e.event == "section.written" for e in events)
    assert any(e.event == "critic.score" for e in events)
    assert any(e.event == "completed" for e in events)
    assert not any(e.event == "failed" for e in events)


@pytest.mark.asyncio
async def test_pipeline_requests_revision_when_critic_fails(sample_request) -> None:
    llm = FakeLLMClient(critic_results=[_critique(passed=False, weak=["hook"]), _critique(passed=True)])
    bus = EventBus()
    pipeline = Pipeline(
        outline_agent=OutlineAgent(llm=llm),
        hook_agent=HookAgent(llm=llm),
        writer_agent=WriterAgent(llm=llm),
        critic_agent=CriticAgent(llm=llm, pass_threshold=8.0),
        event_bus=bus,
        max_revisions=2,
        pass_threshold=8.0,
    )
    events: list = []

    async def collect() -> None:
        async for event in bus.subscribe("job-1"):
            events.append(event)
            if event.event in ("completed", "failed"):
                break

    task = asyncio.create_task(collect())
    state = await pipeline.run("job-1", sample_request)
    await task

    assert state.revision_count == 1
    assert state.critic_feedback.assessment.passed is True
    assert state.status == "completed"


@pytest.mark.asyncio
async def test_pipeline_respects_max_revisions(sample_request) -> None:
    llm = FakeLLMClient(critic_results=[_critique(passed=False, weak=["hook"])] * 5)
    bus = EventBus()
    pipeline = Pipeline(
        outline_agent=OutlineAgent(llm=llm),
        hook_agent=HookAgent(llm=llm),
        writer_agent=WriterAgent(llm=llm),
        critic_agent=CriticAgent(llm=llm, pass_threshold=8.0),
        event_bus=bus,
        max_revisions=1,
        pass_threshold=8.0,
    )
    events: list = []

    async def collect() -> None:
        async for event in bus.subscribe("job-1"):
            events.append(event)
            if event.event in ("completed", "failed"):
                break

    task = asyncio.create_task(collect())
    state = await pipeline.run("job-1", sample_request)
    await task

    assert state.revision_count == 1
    assert state.status == "completed"


@pytest.mark.asyncio
async def test_pipeline_supports_configurable_steps(sample_request) -> None:
    llm = FakeLLMClient(critic_results=[_critique(passed=True)])
    bus = EventBus()
    pipeline = Pipeline(
        outline_agent=OutlineAgent(llm=llm),
        hook_agent=HookAgent(llm=llm),
        writer_agent=WriterAgent(llm=llm),
        critic_agent=CriticAgent(llm=llm, pass_threshold=8.0),
        event_bus=bus,
        steps=["outline", "writer"],
    )
    events: list = []

    async def collect() -> None:
        async for event in bus.subscribe("job-1"):
            events.append(event)
            if event.event in ("completed", "failed"):
                break

    task = asyncio.create_task(collect())
    state = await pipeline.run("job-1", sample_request, steps=["outline", "writer"])
    await task

    assert state.status == "completed"
    assert any(e.event == "agent.completed" and e.agent == "outline" for e in events)
    assert any(e.event == "section.written" for e in events)
    assert not any(e.event.startswith("critic") for e in events)


@pytest.mark.asyncio
async def test_planner_agent_sets_plan_state() -> None:
    agent = PlannerAgent(llm=FakeLLMClient())
    state = PipelineState(job_id="plan-1", status="running")
    new_state = await agent.run(state, niche="sleep science", goal="grow audience", episodes=3)
    assert new_state.plan is not None
    assert new_state.plan.niche == "sleep science"
    assert new_state.plan.goal == "grow audience"


@pytest.mark.asyncio
async def test_trend_agent_ranks_niche_trends_without_llm() -> None:
    agent = TrendAgent(llm=None)
    state = PipelineState(job_id="trend-1", status="running")
    new_state = await agent.run(state, niche="sleep science")
    assert len(new_state.trends) >= 1
    assert isinstance(new_state.trends[0], Trend)
    assert new_state.trends[0].score > 0


@pytest.mark.asyncio
async def test_competitor_gap_agent_finds_weak_topic_coverage() -> None:
    agent = CompetitorGapAgent()
    state = PipelineState(job_id="gap-1", status="running")
    new_state = await agent.run(state, competitor_videos=[CompetitorVideo(url="https://youtu.be/a", title="Sleep science basics"), CompetitorVideo(url="https://youtu.be/b", title="Cooking pasta")])
    assert new_state.gap_analysis is not None
    assert len(new_state.gap_analysis.gaps) >= 1
    assert len(new_state.gap_analysis.suggestions) >= 1
