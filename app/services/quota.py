"""Per-user daily generation quota (free-tier guard).

Counts generation jobs created since 00:00 UTC for the API-key owner. This is a
coarse anti-abuse limit for the zero-cost deployment, not a billing primitive.
"""

from datetime import datetime, timedelta, timezone

from sqlalchemy import func, select

from app.core.config import settings
from app.models.db import ScriptJob, async_session


def _utc_day_start() -> datetime:
    # Timezone-aware UTC; SQLModel's UTCDateTime stores it correctly on SQLite and PostgreSQL.
    now = datetime.now(timezone.utc)
    return now.replace(hour=0, minute=0, second=0, microsecond=0)


def daily_limit() -> int:
    """0 (or negative) disables the limit."""
    return max(0, int(settings.GENERATION_DAILY_LIMIT_PER_USER))


def reset_at() -> datetime:
    return _utc_day_start() + timedelta(days=1)


def reset_at_iso() -> str:
    return reset_at().isoformat().replace("+00:00", "Z")


async def used_today(owner: str) -> int:
    start = _utc_day_start()
    async with async_session() as session:
        result = await session.execute(
            select(func.count())
            .select_from(ScriptJob)
            .where(ScriptJob.owner == owner, ScriptJob.created_at >= start)
        )
        return int(result.scalar() or 0)


async def quota_snapshot(owner: str) -> dict:
    limit = daily_limit()
    used = await used_today(owner)
    if limit == 0:
        return {
            "owner": owner,
            "used": used,
            "limit": 0,
            "remaining": None,
            "unlimited": True,
            "resets_at": reset_at_iso(),
        }
    return {
        "owner": owner,
        "used": used,
        "limit": limit,
        "remaining": max(0, limit - used),
        "unlimited": False,
        "resets_at": reset_at_iso(),
    }


async def check_and_raise(owner: str) -> None:
    """Raise HTTP 429 with a friendly reset message when the daily limit is reached."""
    limit = daily_limit()
    if limit == 0:
        return
    used = await used_today(owner)
    if used >= limit:
        from fastapi import HTTPException

        raise HTTPException(
            status_code=429,
            detail=(
                f"Daily generation limit reached ({used}/{limit} today). "
                f"Free quota resets at {reset_at_iso()}. "
                "Add GROQ_API_KEY or a paid LLM key to raise the upstream quota."
            ),
        )


def quota_headers(snapshot: dict) -> dict[str, str]:
    headers = {"X-Daily-Quota-Used": str(snapshot["used"])}
    if snapshot.get("limit"):
        headers["X-Daily-Quota-Limit"] = str(snapshot["limit"])
    if snapshot.get("remaining") is not None:
        headers["X-Daily-Quota-Remaining"] = str(snapshot["remaining"])
    return headers


__all__ = [
    "check_and_raise",
    "daily_limit",
    "quota_headers",
    "quota_snapshot",
    "reset_at_iso",
    "used_today",
]
