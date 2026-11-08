from app.agents.base import BaseAgent
from app.pipeline.state import PipelineState
from app.schemas.script import CriticResult, HookScore, WrittenScript
from app.services.llm_client import BaseLLMClient


class CriticAgent(BaseAgent):
    """Scores the script (hook strength, pacing, clarity, repetition) from 1-10 with feedback."""

    name = "critic"

    def __init__(self, llm: BaseLLMClient, pass_threshold: float = 8.0) -> None:
        self.llm = llm
        self.pass_threshold = pass_threshold

    async def run(self, state: PipelineState, **kwargs) -> PipelineState:
        script = WrittenScript(sections=list(state.sections), word_count=sum(s.word_count for s in state.sections))
        result = await self.llm.structured(self._build_prompt(state, script), CriticResult, tool_name="critic_result")
        assessment = result.assessment
        dims = [assessment.hook_strength, assessment.pacing, assessment.clarity, assessment.repetition]
        avg = round(sum(dims) / len(dims), 2) if dims else 0.0
        passed = avg >= self.pass_threshold
        state.critic_feedback = CriticResult(
            assessment=type(assessment)(
                hook_strength=assessment.hook_strength,
                pacing=assessment.pacing,
                clarity=assessment.clarity,
                repetition=assessment.repetition,
                feedback=assessment.feedback or "",
                passed=passed,
            ),
            weak_sections=list(result.weak_sections or []),
        )
        return state

    async def score_hook(self, hook_text: str) -> HookScore:
        """Score a standalone hook variant (used by the Hook A/B testing flow)."""
        result = await self.llm.structured(self._build_hook_prompt(hook_text), HookScore, tool_name="hook_score")
        return HookScore(hook_strength=result.hook_strength, reasoning=result.reasoning or "")

    def _build_hook_prompt(self, hook_text: str) -> str:
        return (
            "You are the Critic Agent. Score a YouTube hook on strength (1-10): curiosity, shock value, clarity.\n\n"
            f"Hook: {hook_text}\n\n"
            "Return JSON: {\"hook_strength\": <float 0-10>, \"reasoning\": \"<brief explanation>\"}."
        )

    def _build_prompt(self, state: PipelineState, script: WrittenScript) -> str:
        request = state.request
        if request is None:
            raise RuntimeError("Request missing for critic evaluation")
        # Keep the prompt token-light but still show the actual copy: a blind critic cannot
        # produce useful revision feedback.
        script_text = "\n".join(f"[{s.section_type}] {s.content}" for s in script.sections)
        if len(script_text) > 6000:
            script_text = script_text[:6000] + "\n...(truncated)"
        return (
            "You are the Critic Agent in a YouTube script generation pipeline.\n\n"
            f"Topic: {request.topic}\n"
            f"Duration: {request.duration_minutes} minutes | Words: {script.word_count}\n\n"
            f"Script:\n{script_text}\n\n"
            "Score hook strength, pacing, clarity, repetition (each 1-10) and give brief feedback.\n\n"
            "Respond with JSON ONLY matching this exact schema, no markdown fences, no commentary:\n"
            "{\n"
            '  "assessment": {\n'
            '    "hook_strength": 0.0, "pacing": 0.0, "clarity": 0.0, "repetition": 0.0,\n'
            '    "feedback": "string", "passed": true\n'
            "  },\n"
            '  "weak_sections": ["hook", "intro", "main_point", "retention_loop", "cta", "outro"]\n'
            "}\n"
            "Each score is a float 0-10. weak_sections is a list of section names that are weak (empty array if none)."
        )
