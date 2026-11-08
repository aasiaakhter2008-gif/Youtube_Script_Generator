from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Response
from pydantic import BaseModel

from app.core.config import settings
from app.core.security import verify_api_key
from app.services.generation import job_pipeline_state
from app.services.tts import tts_service

router = APIRouter(prefix="/scripts", tags=["tts"], dependencies=[Depends(verify_api_key)])


class TTSRequest(BaseModel):
    section_type: Optional[str] = None
    voice: str = "en-US-AriaNeural"


@router.post("/{job_id}/tts")
async def generate_tts(job_id: str, body: TTSRequest) -> Response:
    """Generate TTS audio for a job section (or the full script) and return it as an mp3 file."""
    state = await job_pipeline_state(job_id)
    if state is None:
        raise HTTPException(status_code=404, detail="Script job not found")
    provider = (settings.TTS_PROVIDER or "elevenlabs").lower().strip()
    if provider == "edge":
        try:
            import edge_tts  # noqa: F401
        except ImportError as exc:
            raise HTTPException(status_code=501, detail="TTS not configured: the 'edge-tts' package is not installed. Set TTS_PROVIDER=elevenlabs with ELEVENLABS_API_KEY, or install edge-tts.") from exc
    elif not (settings.ELEVENLABS_API_KEY or "").strip():
        raise HTTPException(status_code=501, detail="TTS not configured: ELEVENLABS_API_KEY is missing. Add an ElevenLabs key to .env (or set TTS_PROVIDER=edge for free local TTS).")
    text = ""
    for section in state.sections:
        source_type = section.section_type.value if hasattr(section.section_type, "value") else str(section.section_type)
        if body.section_type and source_type.lower() != body.section_type.lower():
            continue
        text += (section.content or "").strip() + "\n"
    cleaned = text.strip()
    if not cleaned:
        raise HTTPException(status_code=409, detail="No script content available for TTS")
    try:
        audio = await tts_service.synthesize(text=cleaned, voice=body.voice)
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=503, detail=f"TTS service temporarily unavailable: {exc}") from exc
    return Response(content=audio, media_type="audio/mpeg", headers={"Content-Disposition": 'attachment; filename="tts.mp3"'})
