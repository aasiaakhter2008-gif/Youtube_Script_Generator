from pydantic import BaseModel, Field

from app.eval.benchmarks import BenchmarkTopic
from app.schemas.script import WrittenScript
from app.services.llm_client import BaseLLMClient


class JudgeScore(BaseModel):
    score: float = Field(ge=0, le=10)
    feedback: str = ""
    criteria: dict = Field(default_factory=dict)


class JudgeAgent:
    """Offline quality judge: LLM-as-judge scores a written script against a benchmark topic."""

    def __init__(self, llm: BaseLLMClient) -> None:
        self.llm = llm

    async def judge(self, script: WrittenScript, benchmark: BenchmarkTopic) -> JudgeScore:
        script_text = "\n".join(f"[{s.section_type.value}] {s.content}" for s in script.sections)
        prompt = (
            "You are the offline quality Judge for a YouTube script generation eval suite.\n"
            "Score the script quality from 0 to 10.\n\n"
            f"Topic: {benchmark.topic}\nAudience: {benchmark.audience}\nTone: {benchmark.tone.value}\n"
            f"Duration: {benchmark.duration_minutes} min\nFormat: {benchmark.format.value}\n"
            f"Expected word count: {benchmark.expected_min_words}-{benchmark.expected_max_words}\n\n"
            f"Script:\n{script_text}\n\n"
            'Return JSON: {"score": <0-10>, "feedback": "...", "criteria": {"hook": n, "structure": n, "retention": n, "cta": n, "tone": n}}\n'
            "(criteria scores are 0-10 sub-dimensions; score is the overall quality)."
        )
        return await self.llm.structured(prompt, JudgeScore, tool_name="judge_score")
