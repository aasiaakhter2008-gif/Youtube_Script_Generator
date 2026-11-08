import pytest

from app.eval.benchmarks import BENCHMARK_TOPICS, BenchmarkTopic, get_benchmarks
from app.eval.checks import check_structure, script_word_count
from app.eval.judge import JudgeAgent, JudgeScore
from app.eval.runner import EvalReport, run_eval
from app.schemas.script import Outline, OutlineSection, SectionType, WriterSection, WrittenScript
from app.services.llm_client import BaseLLMClient


def _eval_outline() -> Outline:
    return Outline(
        hook=OutlineSection(section_type=SectionType.HOOK, title="Hook", key_points=[], estimated_duration_seconds=20),
        intro=OutlineSection(section_type=SectionType.INTRO, title="Intro", key_points=[], estimated_duration_seconds=15),
        retention_loop=OutlineSection(section_type=SectionType.RETENTION_LOOP, title="Retention", key_points=[], estimated_duration_seconds=15),
        cta=OutlineSection(section_type=SectionType.CTA, title="CTA", key_points=[], estimated_duration_seconds=10),
        outro=OutlineSection(section_type=SectionType.OUTRO, title="Outro", key_points=[], estimated_duration_seconds=10),
    )


class FakeEvalLLM(BaseLLMClient):
    def __init__(self, judge_score: JudgeScore) -> None:
        self.judge_score = judge_score
        self.writer_responses: list[WriterSection] = [
            WriterSection(section_type=SectionType.HOOK, title="Hook", content="You will not believe what happens during deep sleep tonight and how it changes everything.", b_roll_cues=["talking head"], on_screen_text=["Deep sleep"], word_count=14),
            WriterSection(section_type=SectionType.INTRO, title="Intro", content="Here is why this matters for your health and daily energy.", b_roll_cues=["talking head"], on_screen_text=["Health"], word_count=10),
            WriterSection(section_type=SectionType.RETENTION_LOOP, title="Retention", content="But wait, there is so much more to learn about sleep.", b_roll_cues=["b-roll"], on_screen_text=["More"], word_count=11),
            WriterSection(section_type=SectionType.CTA, title="CTA", content="Subscribe for more science stories and keep your curiosity alive.", b_roll_cues=["logo"], on_screen_text=["Subscribe"], word_count=10),
            WriterSection(section_type=SectionType.OUTRO, title="Outro", content="Thanks so much for watching and see you in the next video.", b_roll_cues=["logo"], on_screen_text=["Thanks"], word_count=11),
        ]
        self.writer_calls = 0

    async def structured(self, prompt, schema, **kwargs):
        if schema is JudgeScore:
            return self.judge_score
        if schema is WriterSection:
            section = self.writer_responses[min(self.writer_calls, len(self.writer_responses) - 1)]
            self.writer_calls += 1
            return section
        raise ValueError(f"Unexpected schema: {schema}")


@pytest.mark.asyncio
async def test_check_structure_flags_missing_cta() -> None:
    benchmark = BenchmarkTopic(topic="Test Topic", duration_minutes=8, expected_min_words=50, expected_max_words=200)
    sections = [
        WriterSection(section_type=SectionType.HOOK, title="Hook", content="A great hook opens with curiosity.", b_roll_cues=["talking head"], on_screen_text=["Hook"], word_count=8),
        WriterSection(section_type=SectionType.INTRO, title="Intro", content="Context matters here.", b_roll_cues=["b-roll"], on_screen_text=["Context"], word_count=5),
        WriterSection(section_type=SectionType.RETENTION_LOOP, title="Retention", content="But wait, more.", b_roll_cues=["b-roll"], on_screen_text=["More"], word_count=4),
        WriterSection(section_type=SectionType.OUTRO, title="Outro", content="Thanks for watching.", b_roll_cues=["logo"], on_screen_text=["Thanks"], word_count=3),
    ]
    issues = check_structure(sections, benchmark)
    assert any("cta" in issue for issue in issues)


@pytest.mark.asyncio
async def test_check_structure_passes_for_complete_script() -> None:
    benchmark = BenchmarkTopic(topic="Test Topic", duration_minutes=8, expected_min_words=50, expected_max_words=200)
    sections = [
        WriterSection(section_type=SectionType.HOOK, title="Hook", content="A great hook opens with curiosity and promises an exciting payoff for viewers.", b_roll_cues=["talking head"], on_screen_text=["Hook"], word_count=12),
        WriterSection(section_type=SectionType.INTRO, title="Intro", content="Context matters here for the audience to stay engaged with the topic.", b_roll_cues=["b-roll"], on_screen_text=["Context"], word_count=11),
        WriterSection(section_type=SectionType.RETENTION_LOOP, title="Retention", content="But wait, there is more context and a twist for retention.", b_roll_cues=["b-roll"], on_screen_text=["More"], word_count=11),
        WriterSection(section_type=SectionType.CTA, title="CTA", content="Subscribe for more content like this and join our community today.", b_roll_cues=["logo"], on_screen_text=["Subscribe"], word_count=10),
        WriterSection(section_type=SectionType.OUTRO, title="Outro", content="Thanks for watching and have a great day everyone.", b_roll_cues=["logo"], on_screen_text=["Thanks"], word_count=8),
    ]
    assert check_structure(sections, benchmark) == []


def test_script_word_count_computes_from_content() -> None:
    assert script_word_count([WriterSection(section_type=SectionType.HOOK, title="Hook", content="one two three", word_count=0)]) == 3


@pytest.mark.asyncio
async def test_judge_agent_returns_structured_score() -> None:
    judge = JudgeAgent(llm=FakeEvalLLM(judge_score=JudgeScore(score=8.5, feedback="Solid hook.", criteria={"hook": 9.0})))
    script = WrittenScript(sections=[], word_count=0)
    benchmark = BenchmarkTopic(topic="Test Topic", duration_minutes=8)
    score = await judge.judge(script, benchmark)
    assert score.score == 8.5
    assert score.feedback == "Solid hook."


@pytest.mark.asyncio
async def test_run_eval_passes_quality_gate() -> None:
    benchmark = BenchmarkTopic(topic="Test Topic", duration_minutes=8, expected_min_words=50, expected_max_words=200)
    report = await run_eval(llm=FakeEvalLLM(judge_score=JudgeScore(score=8.0)), benchmarks=[benchmark])
    assert isinstance(report, EvalReport)
    assert len(report.results) == 1
    assert report.results[0].score == 8.0
    assert report.results[0].passed is True
    assert report.average_score == 8.0
    assert report.passed is True


@pytest.mark.asyncio
async def test_run_eval_fails_when_judge_score_below_threshold() -> None:
    benchmark = BenchmarkTopic(topic="Test Topic", duration_minutes=8, expected_min_words=50, expected_max_words=200)
    report = await run_eval(llm=FakeEvalLLM(judge_score=JudgeScore(score=5.0)), benchmarks=[benchmark])
    assert report.passed is False
    assert report.results[0].passed is False


def test_benchmarks_catalog_has_30_topics() -> None:
    assert len(BENCHMARK_TOPICS) >= 30
    assert get_benchmarks() == BENCHMARK_TOPICS
    assert len(get_benchmarks(niche="sleep")) >= 1
