from typing import Optional

from app.agents.base import BaseAgent
from app.pipeline.state import PipelineState
from app.schemas.script import Channel, ChannelInsight, VideoPerformance
from app.services.llm_client import BaseLLMClient


class InsightsAgent(BaseAgent):
    """Correlates published video performance (views, CTR, retention, comments) with script traits → plain-language insights."""

    name = "insights"

    def __init__(self, llm: BaseLLMClient) -> None:
        self.llm = llm

    async def run(self, state: PipelineState, **kwargs) -> PipelineState:
        channel = kwargs.get("channel")
        performances: list[VideoPerformance] = list(kwargs.get("performances") or [])
        insights: list[ChannelInsight] = []
        for performance in performances:
            insight, action = await self._analyze(state, channel, performance)
            insights.append(ChannelInsight(channel_id=channel.youtube_channel_id if channel else "", video_id=performance.video_id, insight=insight, suggested_action=action))
        state.insights = insights
        return state

    async def _analyze(self, state: PipelineState, channel: Optional[Channel], performance: VideoPerformance) -> tuple:
        llm = self.llm
        prompt = (
            "You are the Insights Agent. Given a published video's performance stats, write one plain-language insight "
            f"for the channel and a suggested action for the next script.\n\n"
            f"Channel: {channel.handle if channel else 'unknown'} (id={channel.youtube_channel_id if channel else 'n/a'})\n"
            f"Video: {performance.video_id}\n"
            f"Views: {performance.views}, CTR: {performance.ctr}, Avg view duration: {performance.avg_view_duration_seconds}s, Comments: {performance.comments_count}\n\n"
            "Respond with JSON: {\"insight\": \"...\", \"suggested_action\": \"...\"}."
        )
        result = await llm.structured(prompt, ChannelInsight, tool_name="channel_insight")
        return result.insight, result.suggested_action
