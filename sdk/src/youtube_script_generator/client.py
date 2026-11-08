import httpx


class YouTubeScriptClient:
    """Small async/sync-capable client for the YouTube Script Generator REST API."""

    def __init__(self, api_key: str, base_url: str = "http://localhost:8000", timeout: float = 30.0) -> None:
        self.api_key = api_key
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout

    def _headers(self) -> dict:
        return {"X-API-Key": self.api_key, "Content-Type": "application/json"}

    async def generate(self, topic: str, audience: str = "General audience", tone: str = "educational", language: str = "English", duration_minutes: int = 8, format: str = "long_form") -> dict:
        async with httpx.AsyncClient(timeout=self.timeout) as client:
            response = await client.post(
                f"{self.base_url}/v1/scripts/generate",
                json={
                    "topic": topic,
                    "audience": audience,
                    "tone": tone,
                    "language": language,
                    "duration_minutes": duration_minutes,
                    "format": format,
                },
                headers=self._headers(),
            )
            response.raise_for_status()
            return response.json()

    async def stream_events(self, job_id: str):
        async def event_stream():
            async with httpx.AsyncClient(timeout=self.timeout, follow_redirects=True) as client:
                async with client.stream("GET", f"{self.base_url}/v1/scripts/{job_id}/stream", headers=self._headers()) as response:
                    async def gen():
                        async for chunk in response.aiter_text():
                            yield chunk

                    return gen()

        return event_stream()

    async def get_script(self, job_id: str) -> dict:
        async with httpx.AsyncClient(timeout=self.timeout) as client:
            response = await client.get(f"{self.base_url}/v1/scripts/{job_id}", headers=self._headers())
            response.raise_for_status()
            return response.json()

    async def export(self, job_id: str, format: str = "md") -> bytes:
        async with httpx.AsyncClient(timeout=self.timeout) as client:
            response = await client.get(f"{self.base_url}/v1/scripts/{job_id}/export", params={"format": format}, headers=self._headers())
            response.raise_for_status()
            return response.content

    async def get_trends(self, niche: str = "technology") -> list:
        async with httpx.AsyncClient(timeout=self.timeout) as client:
            response = await client.get(f"{self.base_url}/v1/trends", params={"niche": niche}, headers=self._headers())
            response.raise_for_status()
            return response.json()

    async def close(self) -> None:
        pass
