from fastapi import APIRouter, Depends

from app.core.security import verify_api_key
from app.services.jobs import job_store

router = APIRouter(prefix="/jobs", tags=["jobs"], dependencies=[Depends(verify_api_key)])


@router.get("")
async def list_jobs() -> list[dict]:
    """In-memory job registry: job id, topic, status, timestamps (no sensitive data)."""
    return [
        {
            "id": job.id,
            "topic": job.topic,
            "status": job.status,
            "created_at": job.created_at.isoformat(),
            "updated_at": job.updated_at.isoformat(),
        }
        for job in job_store._jobs.values()
    ]
