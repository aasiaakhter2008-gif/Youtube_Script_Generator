from app.agents.base import BaseAgent
from app.pipeline.state import PipelineState
from app.schemas.script import DubScript, TranslatedSection
from app.services.llm_client import BaseLLMClient

# Approximate target-language speaking rates (words per minute) used to adapt translations.
_TARGET_WPM = {
    "English": 140,
    "Spanish": 150,
    "Roman Urdu": 130,
    "Arabic": 130,
    "Hindi": 110,
    "Urdu": 90,
}


class TranslationAgent(BaseAgent):
    """Translates the written script into a target language, preserving tone/idioms and adapting to speaking speed."""

    name = "translator"

    def __init__(self, llm: BaseLLMClient) -> None:
        self.llm = llm

    async def run(self, state: PipelineState, **kwargs) -> PipelineState:
        target_language = str(kwargs.get("target_language") or "Urdu")
        source_language = str(state.request.language.value if state.request is not None else "English")
        sections: list[TranslatedSection] = []
        for section in state.sections:
            translated = await self.llm.structured(
                self._translate_prompt(section, target_language, source_language),
                TranslatedSection,
                tool_name="translated_section",
            )
            duration_seconds = translated.duration_seconds or max(1, round(len(section.content.split()) / _TARGET_WPM.get(target_language, 130) * 60))
            sections.append(
                TranslatedSection(
                    source_section_type=section.section_type.value if hasattr(section.section_type, "value") else str(section.section_type),
                    translated_content=translated.translated_content,
                    duration_seconds=duration_seconds,
                )
            )
        state.dub_script = DubScript(language=target_language, source_language=source_language, sections=sections)
        return state

    def _translate_prompt(self, section, target_language: str, source_language: str) -> str:
        source_type = section.section_type.value if hasattr(section.section_type, "value") else str(section.section_type)
        return (
            "You are the Translation Agent. Translate the script section below into the target language.\n\n"
            f"Source language: {source_language}\n"
            f"Target language: {target_language}\n"
            f"Section type: {source_type}\n\n"
            f"Source content: {section.content}\n\n"
            "Preserve tone, idioms and cultural context. Adapt pacing/length to the target language's natural speaking speed.\n"
            "Return JSON: {\"translated_content\": \"...\", \"duration_seconds\": <float>}."
        )
