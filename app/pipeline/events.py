import asyncio
from typing import AsyncGenerator, Optional

from pydantic import BaseModel

from app.schemas.script import CriticResult, WriterSection, WrittenScript


class PipelineEvent(BaseModel):
    """Event emitted during pipeline execution and consumed by the SSE stream."""

    event: str  # agent.started | agent.completed | hook.selected | section.written | critic.score | revision | completed | failed
    job_id: str = ""
    agent: Optional[str] = None
    section: Optional[WriterSection] = None
    assessment: Optional[CriticResult] = None
    weak_sections: Optional[list] = None
    script: Optional[WrittenScript] = None
    error: Optional[str] = None


class EventBus:
    """Simple pub/sub over asyncio.Queue per job_id."""

    def __init__(self) -> None:
        self._queues: dict[str, asyncio.Queue] = {}

    def _get_queue(self, job_id: str) -> asyncio.Queue:
        queue = self._queues.get(job_id)
        if queue is None:
            queue = asyncio.Queue()
            self._queues[job_id] = queue
        return queue

    async def publish(self, event: PipelineEvent) -> None:
        self._get_queue(event.job_id).put_nowait(event)

    def queue(self, job_id: str) -> asyncio.Queue:
        """Expose the per-job queue so the SSE endpoint can add heartbeats/timeouts."""
        return self._get_queue(job_id)

    async def subscribe(self, job_id: str) -> AsyncGenerator[PipelineEvent, None]:
        queue = self._get_queue(job_id)
        while True:
            event = await queue.get()
            yield event
            if event.event in ("completed", "failed"):
                break

    def clear(self, job_id: str) -> None:
        self._queues.pop(job_id, None)


event_bus = EventBus()
