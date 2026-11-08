import asyncio
import logging
from typing import Awaitable, Callable, Optional

from app.pipeline.events import EventBus, PipelineEvent
from app.pipeline.state import PipelineState
from app.schemas.script import ScriptRequest, WrittenScript

logger = logging.getLogger("youtube_script_generator")


class Pipeline:
    """Plain async orchestrator: Outline -> Hook -> Writer -> Critic -> revisions.

    Steps are configurable via the `steps` argument (defaults to the full script flow).
    """

    DEFAULT_STEPS: list = ["outline", "hook", "writer", "critic"]

    def __init__(
        self,
        outline_agent,
        hook_agent,
        writer_agent,
        critic_agent,
        *,
        max_revisions: int = 2,
        pass_threshold: float = 8.0,
        event_bus: Optional[EventBus] = None,
        steps: Optional[list] = None,
        guardrail_agent=None,
        agent_timeout: float = 90.0,
    ) -> None:
        self.outline_agent = outline_agent
        self.hook_agent = hook_agent
        self.writer_agent = writer_agent
        self.critic_agent = critic_agent
        self.guardrail_agent = guardrail_agent
        self.max_revisions = max_revisions
        self.pass_threshold = pass_threshold
        self.event_bus = event_bus or EventBus()
        self.steps = list(steps) if steps is not None else list(self.DEFAULT_STEPS)
        self.agent_timeout = agent_timeout

    async def run(
        self,
        job_id: str,
        request: ScriptRequest,
        *,
        regenerate: Optional[dict] = None,
        steps: Optional[list] = None,
        on_step: Optional[Callable[[str, PipelineState], Awaitable[None]]] = None,
    ) -> PipelineState:
        state = PipelineState(job_id=job_id, request=request, status="running")
        active = list(steps) if steps is not None else list(self.steps)
        regenerate_section = (regenerate or {}).get("section_type")

        if "outline" in active:
            await self._emit(job_id, PipelineEvent(event="agent.started", job_id=job_id, agent="outline"))
            state = await self._run_agent(self.outline_agent, state, "outline")
            await self._emit(job_id, PipelineEvent(event="agent.completed", job_id=job_id, agent="outline"))
            await self._call_on_step(on_step, "outline", state)

        if "hook" in active:
            await self._emit(job_id, PipelineEvent(event="agent.started", job_id=job_id, agent="hook"))
            state = await self._run_agent(self.hook_agent, state, "hook")
            await self._emit(job_id, PipelineEvent(event="hook.selected", job_id=job_id, agent="hook"))
            await self._call_on_step(on_step, "hook", state)

        if "writer" in active:
            await self._emit(job_id, PipelineEvent(event="agent.started", job_id=job_id, agent="writer"))
            state = await self._run_agent(self.writer_agent, state, "writer")
            await self._emit(job_id, PipelineEvent(event="agent.completed", job_id=job_id, agent="writer"))
            for section in state.sections:
                await self._emit(job_id, PipelineEvent(event="section.written", job_id=job_id, section=section))
            await self._call_on_step(on_step, "writer", state)

        if "critic" in active:
            evaluations = 0
            while True:
                await self._emit(job_id, PipelineEvent(event="agent.started", job_id=job_id, agent="critic"))
                state = await self._run_agent(self.critic_agent, state, "critic")
                feedback = state.critic_feedback
                if feedback is None:
                    raise RuntimeError("Critic agent did not return feedback")
                await self._emit(
                    job_id,
                    PipelineEvent(
                        event="critic.score",
                        job_id=job_id,
                        assessment=feedback,
                        weak_sections=feedback.weak_sections,
                    ),
                )
                if feedback.assessment.passed or evaluations >= self.max_revisions:
                    break
                if "writer" not in active:
                    break
                evaluations += 1
                state.revision_count = evaluations
                weak = list(feedback.weak_sections or [])
                if regenerate_section and evaluations == 1:
                    weak = [regenerate_section]
                await self._emit(job_id, PipelineEvent(event="revision", job_id=job_id, agent="writer", weak_sections=weak))
                state = await self._run_agent(
                    self.writer_agent,
                    state,
                    "writer",
                    weak_sections=weak,
                    instruction=feedback.assessment.feedback,
                )
                await self._emit(job_id, PipelineEvent(event="agent.completed", job_id=job_id, agent="writer"))
                for section in state.sections:
                    await self._emit(job_id, PipelineEvent(event="section.written", job_id=job_id, section=section))
                await self._call_on_step(on_step, "writer", state)
            await self._call_on_step(on_step, "critic", state)

        if "guardrails" in active and self.guardrail_agent is not None:
            await self._emit(job_id, PipelineEvent(event="agent.started", job_id=job_id, agent="guardrails"))
            state = await self._run_agent(self.guardrail_agent, state, "guardrails")
            await self._emit(job_id, PipelineEvent(event="agent.completed", job_id=job_id, agent="guardrails"))
            await self._call_on_step(on_step, "guardrails", state)

        state.status = "completed"
        script = WrittenScript(sections=list(state.sections), word_count=sum(s.word_count for s in state.sections))
        await self._emit(job_id, PipelineEvent(event="completed", job_id=job_id, script=script))
        return state

    async def _emit(self, job_id: str, event: PipelineEvent) -> None:
        await self.event_bus.publish(event)

    async def _run_agent(self, agent, state: PipelineState, agent_name: str, **kwargs) -> PipelineState:
        """Run one agent with a hard timeout so a hung LLM call cannot block the pipeline forever."""
        try:
            return await asyncio.wait_for(agent.run(state, **kwargs), timeout=self.agent_timeout)
        except asyncio.TimeoutError as exc:
            raise RuntimeError(f"Agent '{agent_name}' timed out after {self.agent_timeout} seconds") from exc

    async def _call_on_step(self, on_step, step_name: str, state: PipelineState) -> None:
        """Invoke the optional resume hook (persist state). A callback failure never breaks the pipeline."""
        if on_step is None:
            return
        try:
            await on_step(step_name, state)
        except Exception:
            logger.exception("on_step callback failed", extra={"step": step_name})
