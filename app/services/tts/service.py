import hashlib

from app.core.config import settings
from app.services.tts.base import BaseTTSClient


class ElevenLabsTTSClient(BaseTTSClient):
    """ElevenLabs primary TTS client (HTTP API)."""

    def __init__(self, api_key: str, voice_id: str = "pNInz6obpgDQGcFmaJgB") -> None:
        self.api_key = api_key
        self.voice_id = voice_id
        self.base_url = "https://api.elevenlabs.io"

    async def synthesize(self, text: str, voice: str) -> bytes:
        import httpx

        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.post(
                f"{self.base_url}/v1/text-to-speech/{voice}",
                json={
                    "text": text,
                    "model_id": "eleven_multilingual_v2",
                    "voice_settings": {"stability": 0.75, "similarity_boost": 0.75},
                },
                headers={"xi-api-key": self.api_key},
            )
            if response.status_code != 200:
                raise RuntimeError(f"ElevenLabs TTS failed with status {response.status_code}: {response.text[:300]}")
            return response.content


class EdgeTTSClient(BaseTTSClient):
    """Edge TTS free fallback (uses the optional `edge-tts` python package)."""

    def __init__(self, voice: str = "en-US-AriaNeural") -> None:
        self.voice = voice

    async def synthesize(self, text: str, voice: str) -> bytes:
        try:
            import os
            import tempfile
            from edge_tts import Communicate
        except ImportError as exc:  # pragma: no cover
            raise RuntimeError("Edge TTS client requested but the 'edge-tts' package is not installed") from exc
        communicate = Communicate(text=text, voice=voice or self.voice)
        tmp = tempfile.NamedTemporaryFile(suffix=".mp3", delete=False)
        path = tmp.name
        tmp.close()
        try:
            communicate.save(path)
            with open(path, "rb") as fh:
                return fh.read()
        finally:
            os.unlink(path)


class TTSService:
    """TTS facade with content-hash cache to avoid repeat synthesis cost."""

    def __init__(self, client: BaseTTSClient) -> None:
        self.client = client
        self._cache: dict[str, bytes] = {}

    async def synthesize(self, text: str, voice: str) -> bytes:
        key = hashlib.sha256(f"{type(self.client).__name__}|{text}|{voice}".encode("utf-8")).hexdigest()
        audio = self._cache.get(key)
        if audio is None:
            audio = await self.client.synthesize(text, voice)
            self._cache[key] = audio
        return audio


def make_tts_service() -> TTSService:
    provider = (settings.TTS_PROVIDER or "elevenlabs").lower()
    if provider in ("edge", "edge_tts", "fallback"):
        return TTSService(EdgeTTSClient(voice=settings.TTS_VOICE))
    return TTSService(ElevenLabsTTSClient(api_key=settings.ELEVENLABS_API_KEY, voice_id=settings.TTS_VOICE))


tts_service = make_tts_service()
