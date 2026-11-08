from datetime import datetime, timezone
from typing import Optional


class FeedbackService:
    """Phase 4: human feedback (thumbs up/down + section edits) stored as training signal."""

    def __init__(self) -> None:
        self._records: dict[str, list[dict]] = {}

    async def add_feedback(self, script_job_id: str, section_type: str, rating: str, edited_content: Optional[str] = None) -> dict:
        record = {
            "script_job_id": script_job_id,
            "section_type": section_type,
            "rating": rating,  # "up" | "down"
            "edited_content": edited_content,
            "created_at": datetime.now(timezone.utc).isoformat(),
        }
        self._records.setdefault(script_job_id, []).append(record)
        return record

    async def list_feedback(self, script_job_id: str) -> list[dict]:
        return list(self._records.get(script_job_id, []))

    async def clear(self, script_job_id: str) -> None:
        self._records.pop(script_job_id, None)


feedback_service = FeedbackService()
