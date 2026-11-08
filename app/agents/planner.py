from app.agents.base import BaseAgent
from app.pipeline.state import PipelineState
from app.schemas.plan import SeriesPlan
from app.services.llm_client import BaseLLMClient


class PlannerAgent(BaseAgent):
    """Generates a content calendar / multi-episode series plan from a niche and goal."""

    name = "planner"

    def __init__(self, llm: BaseLLMClient) -> None:
        self.llm = llm

    async def run(self, state: PipelineState, **kwargs) -> PipelineState:
        niche = str(kwargs.get("niche") or (state.request.topic if state.request else "general knowledge"))
        goal = str(kwargs.get("goal") or "grow audience")
        episodes = int(kwargs.get("episodes") or 4)
        prompt = (
            "You are the Planner Agent in a YouTube script generation pipeline.\n\n"
            f"Niche: {niche}\n"
            f"Goal: {goal}\n"
            f"Number of episodes: {episodes}\n\n"
            "Generate a content series plan.\n\n"
            "Respond with JSON ONLY matching this exact schema, no markdown fences, no commentary:\n"
            "{\n"
            '  "niche": "string (the niche, e.g. technology)",\n'
            '  "goal": "string (the series goal)",\n'
            '  "series_title": "string (a catchy series title)",\n'
            '  "episodes": [\n'
            '    {\n'
            '      "title": "string (episode title)",\n'
            '      "angle": "string (the video angle)",\n'
            '      "target_keyword": "string (SEO keyword)",\n'
            '      "format": "long_form or shorts",\n'
            '      "publish_date": "YYYY-MM-DD",\n'
            '      "estimated_duration_minutes": 8,\n'
            '      "notes": "string (brief production notes)"\n'
            "    }\n"
            "  ]\n"
            "}\n"
            "Provide exactly as many episodes as requested. `niche` and `series_title` are required."
        )
        plan = await self.llm.structured(prompt, SeriesPlan, tool_name="series_plan")
        state.plan = plan if isinstance(plan, SeriesPlan) else SeriesPlan.model_validate(plan)
        return state
