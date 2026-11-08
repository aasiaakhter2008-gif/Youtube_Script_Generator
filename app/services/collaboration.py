from datetime import datetime, timezone
from typing import Optional

import httpx

from app.schemas.script import ScriptActivity, ScriptComment, ScriptStatus, Workspace, WorkspaceMember
from app.services.jobs import job_store


class CollaborationService:
    """Phase 4 collaboration: workspaces, members, script comments, activity log, webhooks."""

    def __init__(self) -> None:
        self.workspaces: dict[str, Workspace] = {}
        self.members: dict[str, list[WorkspaceMember]] = {}
        self.comments: dict[str, list[ScriptComment]] = {}
        self.activity: dict[str, list[ScriptActivity]] = {}
        self._webhooks: dict[str, str] = {}

    # ------------------------------------------------------------------ workspaces

    async def create_workspace(self, name: str, owner_id: str) -> Workspace:
        workspace = Workspace(id=f"ws-{name.strip().lower().replace(' ', '-')}-{owner_id[-6:]}", name=name, owner_id=owner_id, created_at=datetime.now(timezone.utc))
        self.workspaces[workspace.id] = workspace
        self.members.setdefault(workspace.id, [])
        return workspace

    async def get_workspace(self, workspace_id: str) -> Optional[Workspace]:
        return self.workspaces.get(workspace_id)

    async def add_member(self, workspace_id: str, user_id: str, role: str = "viewer") -> WorkspaceMember:
        member = WorkspaceMember(id=f"wm-{workspace_id}-{user_id}", workspace_id=workspace_id, user_id=user_id, role=role)
        self.members.setdefault(workspace_id, []).append(member)
        return member

    async def list_members(self, workspace_id: str) -> list[WorkspaceMember]:
        return list(self.members.get(workspace_id, []))

    # ------------------------------------------------------------------ comments

    async def add_comment(self, script_job_id: str, section_type: str, content: str, created_by: str) -> ScriptComment:
        comment = ScriptComment(id=f"cm-{script_job_id}-{len(self.comments.get(script_job_id, []))}", script_job_id=script_job_id, section_type=section_type, content=content, created_by=created_by, created_at=datetime.now(timezone.utc))
        self.comments.setdefault(script_job_id, []).append(comment)
        return comment

    async def list_comments(self, script_job_id: str, section_type: Optional[str] = None) -> list[ScriptComment]:
        comments = list(self.comments.get(script_job_id, []))
        if section_type is None:
            return comments
        return [c for c in comments if c.section_type.lower() == section_type.lower()]

    # ------------------------------------------------------------------ activity

    async def log_activity(self, script_job_id: str, actor: str, action: str, details: Optional[dict] = None) -> ScriptActivity:
        entry = ScriptActivity(id=f"act-{script_job_id}-{len(self.activity.get(script_job_id, []))}", script_job_id=script_job_id, actor=actor, action=action, details=details, created_at=datetime.now(timezone.utc))
        self.activity.setdefault(script_job_id, []).append(entry)
        return entry

    async def list_activity(self, script_job_id: str) -> list[ScriptActivity]:
        return list(self.activity.get(script_job_id, []))

    # ------------------------------------------------------------------ status

    async def set_script_status(self, script_job_id: str, status: ScriptStatus, actor: str = "system") -> ScriptActivity:
        await job_store.update(script_job_id, status=status.value)
        return await self.log_activity(script_job_id, actor=actor, action=f"status_{status.value}", details={"status": status.value})

    # ------------------------------------------------------------------ webhooks

    def register_webhook(self, job_id: str, url: str) -> None:
        if url:
            self._webhooks[job_id] = url

    def unregister_webhook(self, job_id: str) -> None:
        self._webhooks.pop(job_id, None)

    async def dispatch_webhook(self, job_id: str, event: str, payload: dict) -> None:
        url = self._webhooks.get(job_id)
        if not url:
            return
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                await client.post(url, json={"job_id": job_id, "event": event, "data": payload})
        except Exception:
            # graceful degradation: webhook delivery failures must not crash the pipeline
            pass


collaboration_service = CollaborationService()
