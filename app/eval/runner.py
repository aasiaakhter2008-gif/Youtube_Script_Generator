from pydantic import BaseModel, Field

from app.core.config import settings
from app.agents.writer import WriterAgent
from app.eval.benchmarks import BENCHMARK_TOPICS, BenchmarkTopic
from app.eval.checks import check_structure, script_word_count
from app.eval.judge import JudgeAgent, JudgeScore
from app.pipeline.state import PipelineState
from app.schemas.script import Outline, OutlineSection, ScriptRequest, SectionType, WrittenScript
from app.services.llm_client import BaseLLMClient


class EvalResult(BaseModel):
    benchmark: BenchmarkTopic
    score: float
    structure_issues: list[str] = Field(default_factory=list)
    passed: bool = False


class EvalReport(BaseModel):
    results: list[EvalResult] = Field(default_factory=list)
    average_score: float = 0.0
    passed: bool = False


def _eval_outline(duration_minutes: int = 8) -> Outline:
    # One main point per ~1.5 minutes so the benchmark reflects a true full-length script.
    n = max(3, min(8, duration_minutes // 2))
    main_points = [
        OutlineSection(section_type=SectionType.MAIN_POINT, title=f"Point {i + 1}", key_points=[f"point {i + 1}"], estimated_duration_seconds=90)
        for i in range(n)
    ]
    return Outline(
        hook=OutlineSection(section_type=SectionType.HOOK, title="Hook", key_points=[], estimated_duration_seconds=20),
        intro=OutlineSection(section_type=SectionType.INTRO, title="Intro", key_points=[], estimated_duration_seconds=15),
        main_points=main_points,
        retention_loop=OutlineSection(section_type=SectionType.RETENTION_LOOP, title="Retention", key_points=[], estimated_duration_seconds=15),
        cta=OutlineSection(section_type=SectionType.CTA, title="CTA", key_points=[], estimated_duration_seconds=10),
        outro=OutlineSection(section_type=SectionType.OUTRO, title="Outro", key_points=[], estimated_duration_seconds=10),
    )


async def run_eval(llm: BaseLLMClient, benchmarks: list[BenchmarkTopic] | None = None) -> EvalReport:
    """Run offline evals: writer output -> structure checks -> LLM judge score -> aggregate pass/fail."""
    writer = WriterAgent(llm=llm)
    judge = JudgeAgent(llm=llm)
    results: list[EvalResult] = []
    for benchmark in benchmarks or BENCHMARK_TOPICS:
        state = PipelineState(
            job_id=f"eval-{benchmark.topic}",
            status="completed",
            request=ScriptRequest(
                topic=benchmark.topic,
                audience=benchmark.audience,
                tone=benchmark.tone,
                language=benchmark.language,
                duration_minutes=benchmark.duration_minutes,
                format=benchmark.format,
            ),
            outline=_eval_outline(benchmark.duration_minutes),
        )
        state = await writer.run(state)
        script = WrittenScript(sections=list(state.sections), word_count=script_word_count(state.sections))
        score: JudgeScore = await judge.judge(script, benchmark)
        issues = check_structure(script.sections, benchmark)
        threshold = settings.EVAL_MIN_SCORE
        results.append(
            EvalResult(
                benchmark=benchmark,
                score=score.score,
                structure_issues=issues,
                passed=float(score.score) >= threshold and not issues,
            )
        )
    average_score = sum(r.score for r in results) / len(results) if results else 0.0
    return EvalReport(results=results, average_score=average_score, passed=all(r.passed for r in results))
