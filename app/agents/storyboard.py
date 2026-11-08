from app.agents.base import BaseAgent
from app.pipeline.state import PipelineState
from app.schemas.script import Shot, Storyboard
from app.services.llm_client import BaseLLMClient


class StoryboardAgent(BaseAgent):
    """Creates per-section shot lists: shot type, visual description, B-roll keywords, on-screen text, duration."""

    name = "storyboard"

    def __init__(self, llm: BaseLLMClient) -> None:
        self.llm = llm

    async def run(self, state: PipelineState, **kwargs) -> PipelineState:
        shots = []
        for section in state.sections:
            shot = await self.llm.structured(self._shot_prompt(state, section), Shot, tool_name="shot")
            shots.append(
                Shot(
                    section_type=section.section_type.value if hasattr(section.section_type, "value") else str(section.section_type),
                    shot_type=shot.shot_type or "talking_head",
                    visual_description=shot.visual_description or "",
                    b_roll_keywords=list(shot.b_roll_keywords or []),
                    on_screen_text=shot.on_screen_text or "",
                    estimated_duration_seconds=shot.estimated_duration_seconds or max(0.0, float(section.word_count) / 2.33),  # ~140 wpm fallback
                )
            )
        state.storyboard = Storyboard(job_id=state.job_id, shots=shots)
        return state

    def _shot_prompt(self, state: PipelineState, section) -> str:
        source_type = section.section_type.value if hasattr(section.section_type, "value") else str(section.section_type)
        return (
            "You are the Storyboard Agent. For each script section define the shot type and visual plan.\n\n"
            f"Topic: {state.request.topic if state.request else ''}\n"
            f"Section type: {source_type}\n"
            f"Section title: {section.title}\n"
            f"Content: {section.content}\n\n"
            "Return JSON per section: {\"shot_type\": \"talking_head|b_roll|screen_recording|animation\", \"visual_description\": \"...\", \"b_roll_keywords\": [\"...\"], \"on_screen_text\": \"...\", \"estimated_duration_seconds\": <float>}."
        )
