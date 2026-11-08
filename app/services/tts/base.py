from abc import ABC, abstractmethod


class BaseTTSClient(ABC):
    """Provider-agnostic TTS client (ElevenLabs primary, Edge TTS free fallback)."""

    @abstractmethod
    async def synthesize(self, text: str, voice: str) -> bytes:
        raise NotImplementedError
