from typing import Optional

from app.schemas.script import Channel, VideoPerformance


class YouTubeAnalyticsService:
    """Phase 4: stores/fetches published-video performance linked to generated scripts."""

    def __init__(self) -> None:
        self._performances: list[VideoPerformance] = []
        self._channels: dict[str, Channel] = {}

    async def connect_channel(self, channel: Channel) -> Channel:
        self._channels[channel.id] = channel
        return channel

    async def record_performance(self, performance: VideoPerformance) -> VideoPerformance:
        self._performances.append(performance)
        return performance

    async def list_performances(self) -> list[VideoPerformance]:
        return list(self._performances)

    async def get_channel_performances(self, channel_id: str) -> list[VideoPerformance]:
        return [p for p in self._performances if p.script_job_id == channel_id]

    async def get_performance(self, video_id: str) -> Optional[VideoPerformance]:
        for performance in self._performances:
            if performance.video_id == video_id:
                return performance
        return None


youtube_analytics = YouTubeAnalyticsService()
