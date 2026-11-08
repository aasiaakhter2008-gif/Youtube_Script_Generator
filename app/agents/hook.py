from typing import Optional

from app.agents.base import BaseAgent
from app.agents.critic import CriticAgent
from app.pipeline.state import PipelineState
from app.schemas.script import (
    ChosenHook,
    HookEvaluation,
    HookScore,
    HookTestPlan,
    HookVariantList,
    Outline,
    ScriptRequest,
)
from app.services.llm_client import BaseLLMClient


class HookAgent(BaseAgent):
    """Generates 3 hook variations and picks the best one; supports A/B test plans."""

    name = "hook"

    def __init__(self, llm: BaseLLMClient, critic: Optional[CriticAgent] = None) -> None:
        self.llm = llm
        self.critic = critic

    async def run(self, state: PipelineState, **kwargs) -> PipelineState:
        if state.hook_test is not None or kwargs.get("mode") == "tests":
            return await self._run_hook_test_plan(state)
        request = state.request
        outline = state.outline
        if request is None:
            raise RuntimeError("Request missing for hook generation")
        hook = await self.llm.structured(self._build_prompt(request, outline), ChosenHook, tool_name="chosen_hook")
        state.hooks = hook if isinstance(hook, ChosenHook) else ChosenHook.model_validate(hook)
        return state

    async def _run_hook_test_plan(self, state: PipelineState) -> PipelineState:
        """Generate 5 hook variants with distinct psychological angles, score each with the Critic, pick a winner."""
        variants = await self.llm.structured(self._variants_prompt(state), HookVariantList, tool_name="hook_variants")
        candidates = list(variants.variants or [])
        evaluations: list[HookEvaluation] = []
        for idx, variant in enumerate(candidates):
            score = await self.critic.score_hook(variant.text) if self.critic is not None else HookScore(hook_strength=5.0, reasoning="critic unavailable")
            evaluations.append(HookEvaluation(hook_index=idx, hook_strength=score.hook_strength, reasoning=score.reasoning))
        best_idx = -1
        best_score = -1.0
        for i, variant in enumerate(candidates):
            score = evaluations[i].hook_strength if i < len(evaluations) else 0.0
            if score > best_score:
                best_score = score
                best_idx = i
        winner = candidates[best_idx].text if best_idx >= 0 and best_idx < len(candidates) else ""
        state.hook_test = HookTestPlan(
            job_id=state.job_id,
            baseline_hook=winner,
            candidates=candidates,
            evaluations=evaluations,
            metrics=["first_30_sec_retention", "ctr"],
            winner=winner,
        )
        return state

    def _variants_prompt(self, state: PipelineState) -> str:
        request = state.request or _fallback_request()
        outline = state.outline
        lines = [
            "You are the Hook Agent generating A/B test hook variants.",
            "Generate 5 hook variants with distinct psychological angles: curiosity, shock, story, question, bold claim.",
            f"Topic: {request.topic}",
            f"Audience: {request.audience}",
            f"Tone: {request.tone.value}",
            f"Format: {request.format.value}",
        ]
        if outline is not None:
            lines.append(f"Outline hook section: {outline.hook.title}")
            lines.append(f"Hook key points: {', '.join(outline.hook.key_points) or 'n/a'}")
        lines.append("For each variant provide: text, style, angle.")
        return "\n".join(lines)

    def _build_prompt(self, request: ScriptRequest, outline: Outline) -> str:
        return (
            "You are the Hook Agent in a YouTube script generation pipeline.\n\n"
            f"Topic: {request.topic}\n"
            f"Audience: {request.audience}\n"
            f"Tone: {request.tone.value}\n"
            f"Language: {request.language.value}\n"
            f"Format: {request.format.value}\n"
            f"Outline hook section: {outline.hook.title}\n"
            f"Hook key points: {', '.join(outline.hook.key_points) or 'n/a'}\n\n"
            "Generate 3 distinct hook variations for this topic.\n"
            "For each variation provide the hook text and a style hint (question | shock | story | listicle).\n"
            "Then select the single best hook.\n\n"
            "Respond with JSON: {\"text\": \"<best hook>\", \"variations\": [{\"text\": \"...\", \"style\": \"...\"}, ...]}"
        )


def _fallback_request():
    from app.schemas.script import ScriptRequest

    return ScriptRequest(topic="Untitled topic", duration_minutes=5)
