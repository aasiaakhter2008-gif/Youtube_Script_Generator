import logging
from typing import Optional, Sequence

from app.agents.base import BaseAgent
from app.pipeline.state import PipelineState
from app.schemas.script import Outline, SectionType, WriterSection
from app.services.llm_client import BaseLLMClient

logger = logging.getLogger("youtube_script_generator")


def _kind(section_type) -> str:
    return getattr(section_type, "value", str(section_type))


class WriterAgent(BaseAgent):
    """Writes script sections in natural spoken style with [B-roll] / [On-screen text] cues."""

    name = "writer"
    TARGET_WPM = 140

    def __init__(self, llm: BaseLLMClient) -> None:
        self.llm = llm

    async def run(
        self,
        state: PipelineState,
        weak_sections: Optional[Sequence[str]] = None,
        instruction: Optional[str] = None,
    ) -> PipelineState:
        outline = state.outline
        if outline is None:
            raise RuntimeError("Outline missing; writer requires an outline")

        style_examples = await self._style_examples(state)

        if weak_sections is None:
            plan = self._full_plan(outline)
            state.sections = [await self._write_section(state, kind, section, instruction=instruction, style_examples=style_examples) for kind, section in plan]
        else:
            weak_set = {str(w).strip().lower() for w in weak_sections}
            plan = self._plan(outline, list(weak_set))
            fresh_by_kind: dict[str, list[WriterSection]] = {}
            for kind, section in plan:
                fresh_by_kind.setdefault(_kind(kind), []).append(await self._write_section(state, kind, section, instruction=instruction, style_examples=style_examples))
            new_sections: list[WriterSection] = []
            for kind, _section in self._full_plan(outline):
                key = _kind(kind)
                if key in weak_set:
                    queue = fresh_by_kind.get(key)
                    if queue:
                        new_sections.append(queue.pop(0))
                else:
                    existing = next((s for s in state.sections if _kind(s.section_type) == key), None)
                    if existing is not None:
                        new_sections.append(existing)
            state.sections = new_sections
        return state

    def _full_plan(self, outline: Outline) -> list:
        plan: list = [("hook", outline.hook), ("intro", outline.intro)]
        plan += [("main_point", mp) for mp in outline.main_points]
        plan += [
            ("retention_loop", outline.retention_loop),
            ("cta", outline.cta),
            ("outro", outline.outro),
        ]
        return plan

    def _plan(self, outline: Outline, keys: list) -> list:
        section_map = {
            "hook": outline.hook,
            "intro": outline.intro,
            "retention_loop": outline.retention_loop,
            "cta": outline.cta,
            "outro": outline.outro,
        }
        plan = []
        for key in keys:
            normalized = str(key).strip().lower()
            if normalized == "main_point":
                for mp in outline.main_points:
                    plan.append(("main_point", mp))
            elif normalized in section_map:
                plan.append((normalized, section_map[normalized]))
        return plan

    async def _write_section(self, state, kind: str, section, *, instruction: Optional[str], style_examples: Optional[list[str]] = None) -> WriterSection:
        prompt = self._build_prompt(state, kind, section, instruction=instruction, style_examples=style_examples)
        result = await self.llm.structured(prompt, WriterSection, tool_name="writer_section")
        content = (result.content or "").strip()
        return WriterSection(
            section_type=result.section_type if result.section_type is not None else SectionType.HOOK,
            title=section.title,
            content=content,
            b_roll_cues=list(result.b_roll_cues or []),
            on_screen_text=list(result.on_screen_text or []),
            word_count=len(content.split()),
        )

    async def _style_examples(self, state: PipelineState) -> list[str]:
        """Retrieve top-k style chunks for the request's voice profile. Never raises."""
        request = state.request
        voice_id = getattr(request, "voice_profile_id", None) if request else None
        if not voice_id:
            return []
        try:
            from app.services.voice_profiles import voice_profile_service

            profile = await voice_profile_service.get(voice_id)
            if profile is None:
                logger.warning("voice profile not found; writer continues without style examples", extra={"voice_profile_id": voice_id})
                return []
            query_parts = [request.topic]
            outline = state.outline
            hook = getattr(outline, "hook", None) if outline is not None else None
            if hook is not None:
                query_parts.append(getattr(hook, "title", ""))
            results = await voice_profile_service.search(
                query=" ".join(p for p in query_parts if p),
                voice_profile_id=voice_id,
                top_k=4,
                user_id=profile.user_id,
                workspace_id=profile.workspace_id,
            )
            logger.info("writer retrieved style examples", extra={"voice_profile_id": voice_id, "count": len(results)})
            return [r.text for r in results]
        except Exception as exc:  # pragma: no cover - defensive: never crash a generation job
            logger.warning("voice style retrieval failed; writer continues without style examples", extra={"voice_profile_id": voice_id, "error": str(exc)[:200]})
            return []

    def _build_prompt(self, state, kind: str, section, *, instruction: Optional[str], style_examples: Optional[list[str]] = None) -> str:
        request = state.request or _fallback_request()
        hook = state.hooks
        lines = [
            "You are the Writer Agent in a YouTube script generation pipeline.",
            "Write in a natural spoken style (what a human would say on camera).",
            f"Topic: {request.topic}",
            f"Audience: {request.audience}",
            f"Tone: {request.tone.value}",
            f"Language: {request.language.value}",
            f"Target duration: {request.duration_minutes} minutes",
            f"Format: {request.format.value}",
            f"Write the {kind} section of the script.",
            f"Section title: {section.title}",
        ]
        if section.key_points:
            lines.append(f"Key points to cover: {', '.join(section.key_points)}")
        est_seconds = getattr(section, "estimated_duration_seconds", None) or 0
        if est_seconds:
            lines.append(f"Target spoken duration: {est_seconds}s (~{round(est_seconds * self.TARGET_WPM / 60)} words)")
        if hook is not None:
            lines.append(f"Hook text: {hook.text}")
        if style_examples:
            lines.append("Style examples from this author's published videos (match the voice; do NOT copy verbatim):")
            for example in style_examples:
                snippet = str(example)[:400]
                lines.append(f"- {snippet}")
        if state.insights:
            insights_text = " | ".join(f"[{i.video_id}] {i.insight} (action: {i.suggested_action})" for i in state.insights)
            lines.append(f"Channel insights from published video performance: {insights_text}")
        if instruction:
            lines.append(f"Writer instruction: {instruction}")
        lines.append("Write spoken-style copy with [B-roll: ...] and [On-screen text: ...] cues.")
        lines.append("")
        lines.append("JSON ONLY (no fences/commentary), exact schema:")
        lines.append("{")
        lines.append('  "section_type": "<one of: hook|intro|main_point|retention_loop|cta|outro>",')
        lines.append('  "title": "string",')
        lines.append('  "content": "string (the spoken script text)",')
        lines.append('  "b_roll_cues": ["string"],')
        lines.append('  "on_screen_text": ["string"],')
        lines.append('  "word_count": 0')
        lines.append("}")
        return "\n".join(lines)


def _fallback_request():
    from app.schemas.script import ScriptRequest

    return ScriptRequest(topic="Untitled topic", duration_minutes=5)
