from app.agents.base import BaseAgent
from app.pipeline.state import PipelineState
from app.schemas.script import GuardrailsResult
from app.services.llm_client import BaseLLMClient


class GuardrailsAgent(BaseAgent):
    """Flags factual risk, copyright/plagiarism similarity and policy-sensitive content before delivery."""

    name = "guardrails"

    def __init__(self, llm: BaseLLMClient) -> None:
        self.llm = llm

    async def run(self, state: PipelineState, **kwargs) -> PipelineState:
        request = state.request
        if request is None and not state.sections:
            return state
        script_text = "\n".join(s.content for s in state.sections)
        result = await self.llm.structured(self._build_prompt(request, script_text), GuardrailsResult, tool_name="guardrails_result")
        state.guardrails = result
        return state

    def _build_prompt(self, request, script_text: str):
        topic = request.topic if request is not None else "unknown"
        return (
            "You are the Guardrails Agent. Review the script for factual risk, copyright/plagiarism similarity and policy-sensitive content.\n\n"
            f"Topic: {topic}\n\n"
            f"Script: {script_text[:4000]}\n\n"
            "Return JSON: {\"factual_risk\": true/false, \"copyright_similarity\": <float 0-1>, \"policy_flags\": [\"...\"], \"blocked\": true/false} "
            "(blocked = true if the script should not be delivered)."
        )
