import logging
import re
from typing import Optional

from app.models.db import ScriptJob, async_session
from app.pipeline.events import PipelineEvent, event_bus
from app.pipeline.runner import Pipeline
from app.pipeline.state import PipelineState
from app.schemas.script import ScriptRequest, WriterSection, WrittenScript
from app.services import llm_runtime
from app.services.jobs import job_store
from app.services.webhooks import webhook_dispatcher

logger = logging.getLogger("youtube_script_generator")


async def job_pipeline_state(job_id: str) -> Optional[PipelineState]:
    """Build a PipelineState from a stored script job's final written script (for action endpoints)."""
    job = await job_store.get(job_id)
    if job is None:
        return None
    sections: list[WriterSection] = []
    final_script = job.final_script
    if final_script is not None:
        payload = final_script.get("sections") if isinstance(final_script, dict) else final_script
        for section in payload or []:
            sections.append(WriterSection.model_validate(section))
    return PipelineState(job_id=job_id, status="completed", request=job.request, sections=sections)


def _readable_error(exc: Exception) -> str:
    text = re.sub(r"\s+", " ", str(exc) or "").strip()
    if not text:
        text = exc.__class__.__name__
    if "all llm providers busy" in text.lower():
        # FallbackLLMClient already builds a readable "Gemini overloaded ... try again in ~1 minute" message
        if "try again" not in text.lower():
            text = f"{text}. Please try again in ~1 minute."
        return text
    if "timed out" in text.lower():
        return f"{text} — agent exceeded the LLM time limit; please retry."
    if "blocked by guardrails" in text.lower():
        return text
    return text[:300]


def _register_llm_hook() -> None:
    async def _hook(ev: dict) -> None:
        job_id = ev.get("job_id") or llm_runtime.current_job_id() or ""
        message = ev.get("message") or "Model busy — retrying with fallback model..."
        await event_bus.publish(PipelineEvent(event="llm.retry", job_id=job_id, agent=None, error=message))

    llm_runtime.set_llm_event_hook(_hook)


def _make_step_callback(job_id: str):
    async def _on_step(step_name: str, current_state: PipelineState) -> None:
        try:
            await _persist_pipeline_step(job_id, step_name, current_state)
        except Exception:
            logger.exception("failed to persist pipeline state", extra={"job_id": job_id, "step": step_name})

    return _on_step


async def _persist_pipeline_step(job_id: str, step_name: str, state: PipelineState) -> None:
    async with async_session() as session:
        row = await session.get(ScriptJob, job_id)
        if row is None:
            job = await job_store.get(job_id)
            owner = job.owner if job is not None else "global"
            row = ScriptJob(id=job_id, topic=state.request.topic if state.request else "", status="running", owner=owner, payload={})
            session.add(row)
        payload = dict(row.payload or {})
        completed = list(payload.get("completed_steps") or [])
        if step_name not in completed:
            completed.append(step_name)
        payload["completed_steps"] = completed
        payload["pipeline_state"] = state.model_dump(mode="json")
        if state.request is not None:
            request = state.request
            payload.setdefault("audience", request.audience)
            payload.setdefault("tone", request.tone.value)
            payload.setdefault("language", request.language.value)
            payload.setdefault("duration_minutes", request.duration_minutes)
            payload.setdefault("format", request.format.value)
            payload.setdefault("topic", request.topic)
        row.payload = payload
        row.status = "running"
        await session.commit()


async def _mark_pipeline_state_completed(job_id: str) -> None:
    async with async_session() as session:
        row = await session.get(ScriptJob, job_id)
        if row is None:
            return
        payload = dict(row.payload or {})
        completed = list(payload.get("completed_steps") or [])
        if "completed" not in completed:
            completed.append("completed")
        payload["completed_steps"] = completed
        row.payload = payload
        row.status = "completed"
        await session.commit()


async def _run_pipeline_and_finalize(
    job_id: str,
    pipeline: Pipeline,
    request: ScriptRequest,
    *,
    regenerate: Optional[dict] = None,
    steps: Optional[list] = None,
) -> None:
    llm_runtime.set_current_job_id(job_id)
    _register_llm_hook()
    try:
        state = await pipeline.run(
            job_id=job_id,
            request=request,
            regenerate=regenerate,
            steps=steps,
            on_step=_make_step_callback(job_id),
        )
        if state.guardrails is not None and state.guardrails.blocked:
            raise RuntimeError("Script blocked by guardrails")
        final_script = WrittenScript(sections=list(state.sections), word_count=sum(s.word_count for s in state.sections))
        await job_store.update(
            job_id,
            status="completed",
            final_script=final_script.model_dump(),
            outline=state.outline.model_dump() if state.outline is not None else None,
            critique=state.critic_feedback.model_dump() if state.critic_feedback is not None else None,
        )
        await job_store.publish(PipelineEvent(event="completed", job_id=job_id, script=final_script))
        await _persist_final(job_id, final_script, state.outline, state.critic_feedback)
        await _mark_pipeline_state_completed(job_id)
        await webhook_dispatcher.dispatch(job_id, "completed", {"script": final_script.model_dump()})
    except Exception as exc:  # noqa: BLE001
        logger.exception("generation failed", extra={"job_id": job_id})
        message = _readable_error(exc)
        await job_store.update(job_id, status="failed", error=message)
        await job_store.publish(PipelineEvent(event="failed", job_id=job_id, error=message))
        await webhook_dispatcher.dispatch(job_id, "failed", {"error": message})
    finally:
        try:
            await _persist_model_usage(job_id)
        except Exception:
            logger.exception("failed to persist model usage", extra={"job_id": job_id})
        llm_runtime.clear_model_usage(job_id)
        llm_runtime.set_current_job_id(None)
        llm_runtime.set_llm_event_hook(None)


async def _persist_model_usage(job_id: str) -> None:
    usage = llm_runtime.model_usage_for_job(job_id)
    if not usage:
        return
    job = await job_store.get(job_id)
    if job is not None:
        # Keep it on the in-memory job too: GET reads the in-memory state first, and the
        # runtime registry is cleared right after this function returns.
        job.model_usage = usage
    async with async_session() as session:
        row = await session.get(ScriptJob, job_id)
        if row is None:
            return
        payload = dict(row.payload or {})
        payload["model_usage"] = usage
        row.payload = payload
        await session.commit()


async def run_generation_job(job_id: str, pipeline: Pipeline) -> None:
    """Background task entrypoint: runs the plain-async pipeline for a job."""
    job = await job_store.get(job_id)
    if job is None:
        logger.warning("generation requested for unknown job", extra={"job_id": job_id})
        return
    await job_store.update(job_id, status="running", error=None)
    logger.info("generation started", extra={"job_id": job_id, "topic": job.topic})
    await _run_pipeline_and_finalize(job_id, pipeline, job.request, regenerate=job.regenerate or None, steps=None)


async def resume_generation_job(job_id: str, pipeline: Pipeline) -> None:
    """Resume a failed job from the last completed step (outline -> hook -> writer -> critic)."""
    async with async_session() as session:
        row = await session.get(ScriptJob, job_id)
        if row is None or not (row.payload or {}).get("pipeline_state"):
            logger.warning("resume requested but no resumable state", extra={"job_id": job_id})
            await job_store.publish(
                PipelineEvent(event="failed", job_id=job_id, error="No resumable pipeline state for this job. Create a new generation instead.")
            )
            return
        payload = row.payload or {}
        completed = list(payload.get("completed_steps") or [])
        try:
            state = PipelineState.model_validate(payload["pipeline_state"])
        except Exception as exc:
            logger.exception("resumable state invalid", extra={"job_id": job_id})
            await job_store.publish(PipelineEvent(event="failed", job_id=job_id, error=f"Resumable state is invalid: {exc}"))
            return
        request = state.request or ScriptRequest(topic=row.topic or "Resume", duration_minutes=5)
        steps = [s for s in ("outline", "hook", "writer") if s not in completed]
        if "critic" not in steps:
            steps = steps + ["critic"]

    job = await job_store.get(job_id)
    if job is None:
        job = await job_store.adopt(job_id=job_id, topic=row.topic or request.topic, request=request, owner=row.owner)
    await job_store.update(job_id, status="running", error=None)
    logger.info("resuming generation", extra={"job_id": job_id, "steps": steps})
    await _run_pipeline_and_finalize(job_id, pipeline, request, regenerate=None, steps=steps)


async def _persist_final(job_id: str, final_script: WrittenScript, outline, critique) -> None:
    async with async_session() as session:
        job_row = (await session.get(ScriptJob, job_id))
        if job_row is None:
            job_row = ScriptJob(id=job_id, topic="", status="completed")
            session.add(job_row)
        job_row.status = "completed"
        job_row.final_script = final_script.model_dump()
        job_row.outline = outline.model_dump() if outline is not None else None
        job_row.critique = critique.model_dump() if critique is not None else None
        await session.commit()
