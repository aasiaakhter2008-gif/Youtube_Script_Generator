import pytest

from app.agents.critic import CriticAgent
from app.agents.hook import HookAgent
from app.agents.storyboard import StoryboardAgent
from app.agents.translator import TranslationAgent
from app.pipeline.state import PipelineState
from app.schemas.script import (
    DubScript,
    HookScore,
    HookTestPlan,
    HookTestResult,
    HookVariant,
    HookVariantList,
    ScriptRequest,
    SectionType,
    Shot,
    Storyboard,
    TranslatedSection,
    WriterSection,
)
from app.services.export import export_storyboard
from app.services.hook_tests import hook_test_store
from app.services.tts import TTSService
from app.services.tts.base import BaseTTSClient
from app.services.llm_client import BaseLLMClient


class FakePhase3LLM(BaseLLMClient):
    def __init__(self) -> None:
        self.calls = 0

    async def structured(self, prompt, schema, **kwargs):
        if schema is HookVariantList:
            return HookVariantList(
                variants=[
                    HookVariant(text="Did you know your brain cleans itself while you sleep?", style="curiosity", angle="curiosity"),
                    HookVariant(text="This one sleep trick changed everything", style="story", angle="story"),
                ]
            )
        if schema is HookScore:
            self.calls += 1
            return HookScore(hook_strength=5.0 + self.calls, reasoning="decent hook")
        if schema is TranslatedSection:
            return TranslatedSection(source_section_type="hook", translated_content="Translation: hook content", duration_seconds=30.0)
        if schema is Shot:
            return Shot(
                section_type="hook",
                shot_type="b_roll",
                visual_description="Animation of the brain cleaning itself",
                b_roll_keywords=["brain scan", "sleeping brain"],
                on_screen_text="Deep sleep",
                estimated_duration_seconds=20.0,
            )
        raise ValueError(f"Unexpected schema: {schema}")


@pytest.mark.asyncio
async def test_hook_agent_generates_hook_test_plan() -> None:
    llm = FakePhase3LLM()
    critic = CriticAgent(llm=llm)
    agent = HookAgent(llm=llm, critic=critic)
    state = PipelineState(
        job_id="job-1",
        status="completed",
        request=ScriptRequest(topic="The Science of Sleep", duration_minutes=8, format="long_form"),
        sections=[WriterSection(section_type=SectionType.HOOK, title="Hook", content="You will not believe what happens during deep sleep.", word_count=10)],
    )
    new_state = await agent.run(state, mode="tests")
    plan = new_state.hook_test
    assert plan is not None
    assert isinstance(plan, HookTestPlan)
    assert len(plan.candidates) == 2
    assert len(plan.evaluations) == 2
    assert plan.metrics == ["first_30_sec_retention", "ctr"]
    assert plan.winner  # best-scored variant becomes the winner / baseline


@pytest.mark.asyncio
async def test_hook_test_store_result_lifecycle() -> None:
    result = HookTestResult(job_id="job-9", winner_hook="Did you know your brain cleans itself while you sleep?", metrics={"first_30_sec_retention": 0.42, "ctr": 0.08})
    stored = await hook_test_store.save_result(result)
    assert stored.winner_hook == result.winner_hook
    fetched = await hook_test_store.get_result("job-9")
    assert fetched is not None
    assert fetched.metrics["ctr"] == 0.08
    assert await hook_test_store.get_result("missing-job") is None


@pytest.mark.asyncio
async def test_translation_agent_builds_dub_script() -> None:
    llm = FakePhase3LLM()
    agent = TranslationAgent(llm=llm)
    state = PipelineState(
        job_id="job-2",
        status="completed",
        request=ScriptRequest(topic="The Science of Sleep", duration_minutes=8, format="long_form"),
        sections=[WriterSection(section_type=SectionType.HOOK, title="Hook", content="You will not believe what happens during deep sleep.", word_count=10)],
    )
    new_state = await agent.run(state, target_language="Urdu")
    dub: DubScript = new_state.dub_script
    assert dub is not None
    assert dub.language == "Urdu"
    assert dub.source_language == "English"
    assert len(dub.sections) == 1
    assert dub.sections[0].translated_content


@pytest.mark.asyncio
async def test_storyboard_agent_builds_storyboard() -> None:
    llm = FakePhase3LLM()
    agent = StoryboardAgent(llm=llm)
    state = PipelineState(
        job_id="job-3",
        status="completed",
        request=ScriptRequest(topic="The Science of Sleep", duration_minutes=8, format="long_form"),
        sections=[WriterSection(section_type=SectionType.HOOK, title="Hook", content="You will not believe what happens during deep sleep.", word_count=10)],
    )
    new_state = await agent.run(state)
    storyboard: Storyboard = new_state.storyboard
    assert storyboard is not None
    assert len(storyboard.shots) == 1
    assert storyboard.shots[0].shot_type == "b_roll"


def test_tts_service_caches_by_content_hash() -> None:
    class FakeTTSClient(BaseTTSClient):
        def __init__(self) -> None:
            self.calls = 0

        async def synthesize(self, text: str, voice: str) -> bytes:
            self.calls += 1
            return b"fake-audio-bytes"

    client = FakeTTSClient()
    service = TTSService(client)
    import asyncio

    async def _run() -> tuple:
        first = await service.synthesize("hello world", "en-US-AriaNeural")
        second = await service.synthesize("hello world", "en-US-AriaNeural")
        third = await service.synthesize("different text", "en-US-AriaNeural")
        return first, second, third, client.calls

    first, second, third, calls = asyncio.run(_run())
    assert first == second == b"fake-audio-bytes"
    assert third == b"fake-audio-bytes"
    assert calls == 2  # one for same text+voice, one for different text


def test_export_storyboard_csv() -> None:
    storyboard = Storyboard(job_id="job-4", shots=[])
    from app.schemas.script import Shot

    storyboard.shots.append(Shot(section_type="hook", shot_type="b_roll", visual_description="Brain animation", b_roll_keywords=["brain scan"], on_screen_text="Deep sleep", estimated_duration_seconds=20.0))
    file_bytes, media_type = export_storyboard(storyboard, "csv")
    content = file_bytes.decode("utf-8")
    assert "section_type" in content
    assert "Brain animation" in content
    assert media_type.startswith("text/csv")
