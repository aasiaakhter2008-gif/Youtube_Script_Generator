from app.agents.base import BaseAgent
from app.pipeline.state import PipelineState
from app.schemas.script import Outline, ScriptRequest
from app.services.llm_client import BaseLLMClient


class OutlineAgent(BaseAgent):
    """Generates the structured YouTube outline: Hook → Intro → Main points → Retention → CTA → Outro."""

    name = "outline"

    def __init__(self, llm: BaseLLMClient) -> None:
        self.llm = llm

    async def run(self, state: PipelineState, **kwargs) -> PipelineState:
        request = state.request or _fallback_request()
        outline = await self.llm.structured(self._build_prompt(request), Outline, tool_name="outline")
        state.outline = outline if isinstance(outline, Outline) else Outline.model_validate(outline)
        return state

    def _build_prompt(self, request: ScriptRequest) -> str:
        return (
            "You are the Outline Agent in a YouTube script generation pipeline.\n\n"
            f"Topic: {request.topic}\n"
            f"Audience: {request.audience}\n"
            f"Tone: {request.tone.value}\n"
            f"Language: {request.language.value}\n"
            f"Target duration: {request.duration_minutes} minutes\n"
            f"Format: {request.format.value}\n\n"
            "Create a script outline structured as:\n"
            "1. Hook\n2. Intro\n3. Main points (2-4 main points)\n4. Retention loop\n5. CTA\n6. Outro\n\n"
            "For each section provide a title, key points (2-4 bullets) and an estimated duration in seconds.\n\n"
            "Respond with JSON ONLY matching this exact schema, no markdown fences, no commentary:\n"
            "{\n"
            '  "hook": {"section_type": "hook", "title": "string", "key_points": ["string"], "estimated_duration_seconds": 15},\n'
            '  "intro": {"section_type": "intro", "title": "string", "key_points": ["string"], "estimated_duration_seconds": 30},\n'
            '  "main_points": [\n'
            '    {"section_type": "main_point", "title": "string", "key_points": ["string"], "estimated_duration_seconds": 60}\n'
            "  ],\n"
            '  "retention_loop": {"section_type": "retention_loop", "title": "string", "key_points": ["string"], "estimated_duration_seconds": 30},\n'
            '  "cta": {"section_type": "cta", "title": "string", "key_points": ["string"], "estimated_duration_seconds": 15},\n'
            '  "outro": {"section_type": "outro", "title": "string", "key_points": ["string"], "estimated_duration_seconds": 15}\n'
            "}\n"
            "Every section is REQUIRED. key_points is a list of 2-4 short strings. estimated_duration_seconds is an integer."
        )


def _fallback_request():
    from app.schemas.script import ScriptRequest

    return ScriptRequest(topic="Untitled topic", duration_minutes=5)
