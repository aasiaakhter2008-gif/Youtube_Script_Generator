from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from app.agents.insights import InsightsAgent
from app.core.security import verify_api_key
from app.schemas.script import Channel, ChannelInsight, VideoPerformance
from app.services.llm_client import get_llm_client
from app.services.youtube import youtube_analytics

router = APIRouter(prefix="/youtube", tags=["youtube"], dependencies=[Depends(verify_api_key)])


class ChannelCreate(BaseModel):
    owner_user_id: str = ""
    youtube_channel_id: str = ""
    handle: str = ""


@router.post("/channels", response_model=Channel)
async def connect_channel(body: ChannelCreate) -> Channel:
    channel = Channel(id=f"ch-{body.youtube_channel_id}", owner_user_id=body.owner_user_id, youtube_channel_id=body.youtube_channel_id, handle=body.handle, created_at=datetime.now(timezone.utc))
    return await youtube_analytics.connect_channel(channel)


@router.post("/channels/{channel_id}/videos", response_model=VideoPerformance)
async def record_video_performance(performance: VideoPerformance) -> VideoPerformance:
    if not performance.video_id:
        raise HTTPException(status_code=422, detail="video_id is required")
    return await youtube_analytics.record_performance(performance)


@router.post("/channels/{channel_id}/insights", response_model=list[ChannelInsight])
async def channel_insights(channel_id: str, performances: list[VideoPerformance]) -> list[ChannelInsight]:
    insights_agent = InsightsAgent(llm=get_llm_client(role="critic"))
    insights: list[ChannelInsight] = []
    for performance in performances:
        insight, action = await insights_agent._analyze(None, None, performance)
        insights.append(ChannelInsight(channel_id=channel_id, video_id=performance.video_id, insight=insight, suggested_action=action))
    return insights
