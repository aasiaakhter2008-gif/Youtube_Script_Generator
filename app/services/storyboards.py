from typing import Optional

from app.schemas.script import Storyboard


class StoryboardStore:
    """In-memory storyboard cache per job (Phase 3 item 7; move to DB later)."""

    def __init__(self) -> None:
        self._boards: dict[str, Storyboard] = {}

    async def save(self, storyboard: Storyboard) -> Storyboard:
        self._boards[storyboard.job_id] = storyboard
        return storyboard

    async def get(self, job_id: str) -> Optional[Storyboard]:
        return self._boards.get(job_id)

    async def delete(self, job_id: str) -> None:
        self._boards.pop(job_id, None)


storyboard_store = StoryboardStore()
