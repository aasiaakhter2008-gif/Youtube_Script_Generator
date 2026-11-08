import asyncio
from datetime import datetime, timezone
from typing import AsyncGenerator, Optional
from uuid import uuid4

from app.pipeline.events import PipelineEvent, event_bus
from app.schemas.script import ScriptRequest


class JobState:
    """In-memory job lifecycle state driving the SSE stream + background runner."""

    def __init__(
        self,
        *,
        job_id: str,
        status: str = "pending",
        topic: str = "",
        request: Optional[ScriptRequest] = None,
        owner: str = "global",
        outline: Optional[dict] = None,
        final_script: Optional[dict] = None,
        critique: Optional[dict] = None,
        regenerate: Optional[dict] = None,
        error: Optional[str] = None,
    ) -> None:
        self.id = job_id
        self.status = status
        self.topic = topic
        self.owner = owner
        self.request = request
        self.outline = outline
        self.final_script = final_script
        self.critique = critique
        self.regenerate = regenerate or {}
        self.error = error
        self.model_usage: dict[str, str] = {}
        self.created_at = datetime.now(timezone.utc)
        self.updated_at = datetime.now(timezone.utc)


class JobStore:
    """In-memory job registry with pub/sub for SSE events."""

    def __init__(self) -> None:
        self._jobs: dict[str, JobState] = {}
        self._queues: dict[str, asyncio.Queue] = {}
        self._last_event: dict[str, PipelineEvent] = {}

    async def create(
        self,
        *,
        topic: str,
        request: Optional[ScriptRequest],
        regenerate: Optional[dict] = None,
        owner: str = "global",
    ) -> JobState:
        job = JobState(
            job_id=str(uuid4()),
            status="pending",
            topic=topic,
            request=request,
            owner=owner,
            regenerate=regenerate,
        )
        self._jobs[job.id] = job
        return job

    async def adopt(
        self,
        *,
        job_id: str,
        topic: str,
        request: Optional[ScriptRequest],
        owner: str = "global",
    ) -> JobState:
        """Register an existing (possibly persisted) job id back into the in-memory store, e.g. for resume-after-restart."""
        job = JobState(
            job_id=job_id,
            status="running",
            topic=topic,
            request=request,
            owner=owner,
        )
        self._jobs[job_id] = job
        return job

    async def get(self, job_id: str) -> Optional[JobState]:
        return self._jobs.get(job_id)

    async def update(self, job_id: str, **fields) -> Optional[JobState]:
        job = self._jobs.get(job_id)
        if job is None:
            return None
        for key, value in fields.items():
            setattr(job, key, value)
        return job

    async def publish(self, event: PipelineEvent) -> None:
        self._last_event[event.job_id] = event
        queue = self._queues.get(event.job_id)
        if queue is not None:
            queue.put_nowait(event)
        # Terminal events (completed/failed) are published here by the generation service;
        # forward them to the SSE bus so clients never hang after a failure.
        await event_bus.publish(event)

    async def subscribe(self, job_id: str) -> AsyncGenerator[PipelineEvent, None]:
        queue = self._queues.setdefault(job_id, asyncio.Queue())
        while True:
            event = await queue.get()
            yield event
            if event.event in ("completed", "failed"):
                break

    def clear(self, job_id: str) -> None:
        self._queues.pop(job_id, None)


job_store = JobStore()
