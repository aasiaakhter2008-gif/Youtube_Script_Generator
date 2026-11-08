import asyncio
from typing import AsyncGenerator, Optional

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query, Request, Response
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field
from sqlalchemy import select

from app.agents.critic import CriticAgent
from app.agents.hook import HookAgent
from app.agents.outline import OutlineAgent
from app.agents.writer import WriterAgent
from app.core.config import settings
from app.core.security import verify_api_key
from app.models.db import ScriptJob, async_session
from app.pipeline.events import PipelineEvent, event_bus
from app.pipeline.runner import Pipeline
from app.schemas.export import ExportFormat
from app.schemas.script import (
    CriticResult,
    JobAccepted,
    RegenerateSectionRequest,
    ScriptComment,
    ScriptFormat,
    ScriptActivity,
    ScriptJobRead,
    ScriptLanguage,
    ScriptRequest,
    ScriptStatus,
    ScriptSummary,
    Tone,
    WrittenScript,
)
from app.services import llm_runtime, quota
from app.services.collaboration import collaboration_service
from app.services.export import export_script
from app.services.generation import resume_generation_job, run_generation_job
from app.services.jobs import JobState, job_store
from app.services.llm_client import get_llm_client

pipeline = Pipeline(
    outline_agent=OutlineAgent(llm=get_llm_client(role="outline")),
    hook_agent=HookAgent(llm=get_llm_client(role="outline"), critic=CriticAgent(llm=get_llm_client(role="critic"), pass_threshold=settings.CRITIC_PASS_THRESHOLD)),
    writer_agent=WriterAgent(llm=get_llm_client(role="writer")),
    critic_agent=CriticAgent(llm=get_llm_client(role="critic"), pass_threshold=settings.CRITIC_PASS_THRESHOLD),
    max_revisions=settings.MAX_REVISIONS,
    pass_threshold=settings.CRITIC_PASS_THRESHOLD,
    event_bus=event_bus,
    agent_timeout=settings.AGENT_TIMEOUT_SECONDS,
)

router = APIRouter(
    prefix="/scripts",
    tags=["scripts"],
    dependencies=[Depends(verify_api_key)],
)


@router.post("/generate", response_model=JobAccepted, status_code=202)
async def generate_script(
    request: ScriptRequest,
    background_tasks: BackgroundTasks,
    response: Response,
    owner: str = Depends(verify_api_key),
) -> JobAccepted:
    await quota.check_and_raise(owner)
    job = await job_store.create(topic=request.topic, request=request, owner=owner)
    await _persist_new_job(job.id, request, owner)
    snapshot = await quota.quota_snapshot(owner)
    for header, value in quota.quota_headers(snapshot).items():
        response.headers[header] = value
    background_tasks.add_task(run_generation_job, job.id, pipeline)
    return JobAccepted(job_id=job.id, status=job.status)


@router.get("", response_model=list[ScriptSummary])
async def list_scripts(owner: str = Depends(verify_api_key)) -> list[ScriptSummary]:
    stmt = select(ScriptJob).order_by(ScriptJob.created_at.desc())
    if owner != "global":
        stmt = stmt.where(ScriptJob.owner == owner)
    async with async_session() as session:
        result = await session.execute(stmt)
        jobs = list(result.scalars().all())
    summaries = []
    for job in jobs:
        payload = job.payload or {}
        summaries.append(
            ScriptSummary(
                id=job.id,
                topic=job.topic,
                status=ScriptStatus(job.status),
                format=ScriptFormat(str(payload.get("format") or ScriptFormat.LONG_FORM.value)),
                duration_minutes=int(payload.get("duration_minutes") or 0),
                created_at=job.created_at,
            )
        )
    return summaries


@router.get("/quota")
async def get_quota(owner: str = Depends(verify_api_key)) -> dict:
    """Remaining free-tier generation quota for the current API-key owner."""
    return await quota.quota_snapshot(owner)


async def _persist_new_job(job_id: str, request: ScriptRequest, owner: str) -> None:
    """Insert the job row immediately so daily quota counts it even before step 1 persists."""
    async with async_session() as session:
        if await session.get(ScriptJob, job_id) is not None:
            return
        session.add(
            ScriptJob(
                id=job_id,
                topic=request.topic,
                status="pending",
                owner=owner,
                payload={
                    "topic": request.topic,
                    "audience": request.audience,
                    "tone": request.tone.value,
                    "language": request.language.value,
                    "duration_minutes": request.duration_minutes,
                    "format": request.format.value,
                },
            )
        )
        await session.commit()


def _owner_allowed(job_owner: str, requester: str) -> bool:
    """The main global key acts as admin; scoped keys only see their own jobs."""
    return requester == "global" or job_owner == requester


@router.get("/{job_id}/export")
async def export_script_endpoint(
    job_id: str,
    format: ExportFormat = Query(..., description="Export format: txt | md | docx | pdf"),
) -> Response:
    job = await job_store.get(job_id)
    final_script = job.final_script if job is not None else None
    if final_script is None and job_id:
        async with async_session() as session:
            row = (await session.get(ScriptJob, job_id))
            final_script = row.final_script if row is not None else None
    if final_script is None:
        raise HTTPException(status_code=409, detail="Script not ready for export")
    script = WrittenScript.model_validate(final_script)
    resolved_topic = job.topic if job is not None else "YouTube Script"
    file_bytes, media_type = export_script(script, format, topic=resolved_topic)
    return Response(
        content=file_bytes,
        media_type=media_type,
        headers={"Content-Disposition": f'attachment; filename="youtube_script_{job_id}.{format.value}"'},
    )


class ScriptCommentCreate(BaseModel):
    section_type: str = "hook"
    content: str = Field(min_length=1, max_length=5000)
    created_by: str = "user"


class ScriptStatusUpdate(BaseModel):
    status: ScriptStatus
    actor: str = "user"


@router.post("/{job_id}/comments", response_model= ScriptComment)
async def add_script_comment(job_id: str, body: ScriptCommentCreate) -> ScriptComment:
    return await collaboration_service.add_comment(script_job_id=job_id, section_type=body.section_type, content=body.content, created_by=body.created_by)


@router.get("/{job_id}/comments", response_model= list[ScriptComment])
async def list_script_comments(job_id: str, section_type: Optional[str] = Query(None)) -> list[ScriptComment]:
    return await collaboration_service.list_comments(script_job_id=job_id, section_type=section_type)


@router.post("/{job_id}/status", response_model= ScriptActivity)
async def set_script_status(job_id: str, body: ScriptStatusUpdate) -> ScriptActivity:
    return await collaboration_service.set_script_status(script_job_id=job_id, status=body.status, actor=body.actor)


@router.get("/{job_id}/activity", response_model= list[ScriptActivity])
async def list_script_activity(job_id: str) -> list[ScriptActivity]:
    return await collaboration_service.list_activity(script_job_id=job_id)


def _sse(event: PipelineEvent) -> str:
    return f"event: {event.event}\ndata: {event.model_dump_json()}\n\n"


async def _terminal_event(job_id: str) -> Optional[PipelineEvent]:
    """Return a synthetic terminal event when the job already finished (restart / late subscriber)."""
    job = await job_store.get(job_id)
    if job is not None:
        if job.status == "completed":
            script = WrittenScript.model_validate(job.final_script) if job.final_script else None
            return PipelineEvent(event="completed", job_id=job_id, script=script)
        if job.status == "failed":
            return PipelineEvent(event="failed", job_id=job_id, error=job.error or "Generation failed")
    async with async_session() as session:
        row = await session.get(ScriptJob, job_id)
    if row is None:
        return None
    if row.status == "completed":
        script = WrittenScript.model_validate(row.final_script) if row.final_script else None
        return PipelineEvent(event="completed", job_id=job_id, script=script)
    if row.status == "failed":
        return PipelineEvent(event="failed", job_id=job_id, error=row.error or "Generation failed")
    return None


@router.get("/{job_id}/stream")
async def stream_script(job_id: str, request: Request, owner: str = Depends(verify_api_key)) -> StreamingResponse:
    job = await job_store.get(job_id)
    if job is not None:
        if not _owner_allowed(job.owner, owner):
            raise HTTPException(status_code=404, detail="Job not found")
    else:
        async with async_session() as session:
            row = await session.get(ScriptJob, job_id)
        if row is None or not _owner_allowed(row.owner, owner):
            raise HTTPException(status_code=404, detail="Job not found")

    async def event_generator() -> AsyncGenerator[str, None]:
        # A client may connect after the job finished (free-tier cold start / restart).
        # Close immediately with a terminal event instead of hanging forever.
        terminal = await _terminal_event(job_id)
        if terminal is not None:
            yield _sse(terminal)
            return

        queue = event_bus.queue(job_id)
        while True:
            if await request.is_disconnected():
                return
            try:
                event = await asyncio.wait_for(queue.get(), timeout=10)
            except asyncio.TimeoutError:
                terminal = await _terminal_event(job_id)
                if terminal is not None:
                    yield _sse(terminal)
                    return
                yield ": keep-alive\n\n"
                continue
            yield _sse(event)
            if event.event in ("completed", "failed"):
                return

    return StreamingResponse(
        content=event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


@router.get("/{job_id}", response_model=ScriptJobRead)
async def get_script(job_id: str, owner: str = Depends(verify_api_key)) -> ScriptJobRead:
    job = await job_store.get(job_id)
    if job is not None:
        if not _owner_allowed(job.owner, owner):
            raise HTTPException(status_code=404, detail="Script job not found")
        return _to_script_job_read(job)
    async with async_session() as session:
        row = (await session.get(ScriptJob, job_id))
        if row is None or not _owner_allowed(row.owner, owner):
            raise HTTPException(status_code=404, detail="Script job not found")
        payload = row.payload or {}
        return ScriptJobRead(
            id=row.id,
            status=ScriptStatus(row.status),
            topic=row.topic,
            audience=str(payload.get("audience") or "General audience"),
            tone=Tone(str(payload.get("tone") or Tone.EDUCATIONAL.value)),
            language=ScriptLanguage(str(payload.get("language") or ScriptLanguage.ENGLISH.value)),
            duration_minutes=int(payload.get("duration_minutes") or 0),
            format=ScriptFormat(str(payload.get("format") or ScriptFormat.LONG_FORM.value)),
            outline=row.outline,
            final_script=WrittenScript.model_validate(row.final_script) if row.final_script else None,
            critique=_parse_critic(row.critique),
            error=row.error,
            model_usage=dict(payload.get("model_usage") or {}),
            created_at=row.created_at,
            updated_at=row.updated_at,
        )


@router.post("/{job_id}/retry", response_model=JobAccepted, status_code=202)
async def retry_script(job_id: str, background_tasks: BackgroundTasks, owner: str = Depends(verify_api_key)) -> JobAccepted:
    """Resume a failed job from the last completed step (outline -> hook -> writer -> critic)."""
    async with async_session() as session:
        row = await session.get(ScriptJob, job_id)
    if row is None or not _owner_allowed(row.owner, owner) or not (row.payload or {}).get("pipeline_state"):
        raise HTTPException(status_code=409, detail="No resumable pipeline state for this job. Create a new generation instead.")
    background_tasks.add_task(resume_generation_job, job_id, pipeline)
    return JobAccepted(job_id=job_id, status="pending")


@router.post("/{job_id}/regenerate-section", response_model=JobAccepted)
async def regenerate_section(
    job_id: str,
    body: RegenerateSectionRequest,
    background_tasks: BackgroundTasks,
    response: Response,
    owner: str = Depends(verify_api_key),
) -> JobAccepted:
    job = await job_store.get(job_id)
    if job is None or not _owner_allowed(job.owner, owner):
        raise HTTPException(status_code=404, detail="Script job not found")
    await quota.check_and_raise(owner)
    base_request = job.request or ScriptRequest(topic=job.topic or "Unknown topic", duration_minutes=5)
    new_job = await job_store.create(
        topic=base_request.topic,
        request=base_request,
        regenerate={"section_type": body.section_type.value, "instruction": body.instruction},
        owner=owner,
    )
    await _persist_new_job(new_job.id, base_request, owner)
    snapshot = await quota.quota_snapshot(owner)
    for header, value in quota.quota_headers(snapshot).items():
        response.headers[header] = value
    background_tasks.add_task(run_generation_job, new_job.id, pipeline)
    return JobAccepted(job_id=new_job.id, status=new_job.status)


def _event_to_payload(event: PipelineEvent) -> dict:
    return {
        "event": event.event,
        "job_id": event.job_id,
        "agent": event.agent,
        "section": event.section,
        "assessment": event.assessment,
        "weak_sections": event.weak_sections,
        "script": event.script,
        "error": event.error,
    }


def _to_script_job_read(job: JobState) -> ScriptJobRead:
    return ScriptJobRead(
        id=job.id,
        status=ScriptStatus(job.status),
        topic=job.topic,
        audience=job.request.audience if job.request else "General audience",
        tone=job.request.tone if job.request else Tone.EDUCATIONAL,
        language=job.request.language if job.request else ScriptLanguage.ENGLISH,
        duration_minutes=job.request.duration_minutes if job.request else 0,
        format=job.request.format if job.request else ScriptFormat.LONG_FORM,
        outline=job.outline,
        final_script=WrittenScript.model_validate(job.final_script) if job.final_script else None,
        critique=_parse_critic(job.critique),
        error=job.error,
        model_usage=job.model_usage or llm_runtime.model_usage_for_job(job.id),
        created_at=job.created_at,
        updated_at=job.updated_at,
    )


def _parse_critic(critique) -> CriticResult | None:
    if not critique:
        return None
    return CriticResult.model_validate(critique)
