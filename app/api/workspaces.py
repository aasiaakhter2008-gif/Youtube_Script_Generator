from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from app.core.security import verify_api_key
from app.schemas.script import Workspace, WorkspaceMember
from app.services.collaboration import collaboration_service

router = APIRouter(prefix="/workspaces", tags=["workspaces"], dependencies=[Depends(verify_api_key)])


class WorkspaceCreate(BaseModel):
    name: str = Field(min_length=2, max_length=200)
    owner_id: str = Field(min_length=1, max_length=200)


class WorkspaceMemberCreate(BaseModel):
    user_id: str = Field(min_length=1, max_length=200)
    role: str = "viewer"


@router.post("", response_model=Workspace)
async def create_workspace(body: WorkspaceCreate) -> Workspace:
    workspace = await collaboration_service.create_workspace(name=body.name, owner_id=body.owner_id)
    return workspace


@router.get("/{workspace_id}", response_model=Workspace)
async def get_workspace(workspace_id: str) -> Workspace:
    workspace = await collaboration_service.get_workspace(workspace_id)
    if workspace is None:
        raise HTTPException(status_code=404, detail="Workspace not found")
    return workspace


@router.post("/{workspace_id}/members", response_model= WorkspaceMember)
async def add_workspace_member(workspace_id: str, body: WorkspaceMemberCreate) -> WorkspaceMember:
    member = await collaboration_service.add_member(workspace_id=workspace_id, user_id=body.user_id, role=body.role)
    return member


@router.get("/{workspace_id}/members", response_model=list[WorkspaceMember])
async def list_workspace_members(workspace_id: str) -> list[WorkspaceMember]:
    return await collaboration_service.list_members(workspace_id)
