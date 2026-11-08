import pytest

from app.schemas.script import ScriptStatus
from app.services.collaboration import collaboration_service
from app.services.jobs import job_store


@pytest.mark.asyncio
async def test_workspace_crud_and_members() -> None:
    workspace = await collaboration_service.create_workspace(name="My Team", owner_id="user-1")
    assert workspace.id
    assert workspace.owner_id == "user-1"

    fetched = await collaboration_service.get_workspace(workspace.id)
    assert fetched is not None
    assert fetched.name == "My Team"

    member = await collaboration_service.add_member(workspace_id=workspace.id, user_id="user-2", role="editor")
    assert member.role == "editor"
    members = await collaboration_service.list_members(workspace.id)
    assert len(members) == 1
    assert members[0].user_id == "user-2"


@pytest.mark.asyncio
async def test_script_comments_crud_and_filter() -> None:
    job_id = "job-comment-1"
    comment = await collaboration_service.add_comment(script_job_id=job_id, section_type="hook", content="Make the hook more curious.", created_by="user-1")
    assert comment.content == "Make the hook more curious."

    comments = await collaboration_service.list_comments(script_job_id=job_id)
    assert len(comments) == 1
    assert comments[0].section_type == "hook"

    filtered = await collaboration_service.list_comments(script_job_id=job_id, section_type="outro")
    assert filtered == []


@pytest.mark.asyncio
async def test_script_activity_log_and_status_workflow() -> None:
    job = await job_store.create(topic="Sleep science", request=None)
    activity = await collaboration_service.log_activity(script_job_id=job.id, actor="user-1", action="status_draft", details={"status": "draft"})
    assert activity.action == "status_draft"

    updated = await collaboration_service.set_script_status(script_job_id=job.id, status=ScriptStatus.APPROVED, actor="user-1")
    assert updated.action == "status_approved"

    activities = await collaboration_service.list_activity(script_job_id=job.id)
    assert len(activities) == 2
    fetched_job = await job_store.get(job.id)
    assert fetched_job is not None
    assert fetched_job.status == "approved"


def test_webhook_registration_and_dispatch_without_url() -> None:
    collaboration_service.unregister_webhook("job-wh-1")
    # dispatch without registered webhook must be a no-op (no crash)
    import asyncio

    asyncio.run(collaboration_service.dispatch_webhook("job-wh-1", "completed", {"script": {}}))
    collaboration_service.register_webhook("job-wh-1", "http://example.com/hook")
    assert collaboration_service._webhooks.get("job-wh-1") == "http://example.com/hook"
    collaboration_service.unregister_webhook("job-wh-1")
    assert collaboration_service._webhooks.get("job-wh-1") is None
