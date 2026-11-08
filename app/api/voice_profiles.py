from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, Response, UploadFile, File

from app.core.security import verify_api_key
from app.schemas.voice_profile import VoiceProfileCreate, VoiceProfileRead, VoiceProfileSearchRequest, VoiceProfileSearchResult
from app.services.security_utils import MAX_UPLOAD_BYTES, sanitize_untrusted
from app.services.voice_profiles import voice_profile_service

router = APIRouter(prefix="/voice-profiles", tags=["voice-profiles"])


@router.post("", response_model=VoiceProfileRead, status_code=201)
async def create_voice_profile(body: VoiceProfileCreate, owner: str = Depends(verify_api_key)) -> VoiceProfileRead:
    result = await voice_profile_service.create(
        name=body.name,
        texts=body.texts,
        user_id=body.user_id or owner,
        workspace_id=body.workspace_id or "default",
    )
    return VoiceProfileRead(
        id=result.id,
        name=result.name,
        user_id=result.user_id,
        workspace_id=result.workspace_id,
        source=result.source,
        chunk_count=result.chunk_count,
        created_at=None,
    )


@router.post("/search", response_model=list[VoiceProfileSearchResult])
async def search_voice_profiles(body: VoiceProfileSearchRequest, owner: str = Depends(verify_api_key)) -> list[VoiceProfileSearchResult]:
    try:
        results = await voice_profile_service.search(
            query=body.query,
            voice_profile_id=body.voice_profile_id,
            top_k=body.top_k,
            user_id=owner,
        )
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=503, detail=f"Search service temporarily unavailable: {str(exc)[:200]}") from exc
    return [
        VoiceProfileSearchResult(id=r.id, text=r.text, score=r.score, metadata=r.metadata)
        for r in results
    ]


@router.post("/import-file", response_model=VoiceProfileRead, status_code=201)
async def import_voice_profile_file(
    file: UploadFile = File(...),
    name: str = "Imported profile",
    owner: str = Depends(verify_api_key),
) -> VoiceProfileRead:
    suffix = Path(file.filename or "").suffix.lower()
    allowed = {".txt", ".md"}
    if suffix not in allowed:
        raise HTTPException(status_code=415, detail=f"Unsupported file type '{suffix or 'unknown'}'. Allowed: .txt, .md")
    content = await file.read()
    if len(content) > MAX_UPLOAD_BYTES:
        raise HTTPException(status_code=413, detail="File too large. Maximum size is 5 MB.")
    try:
        text = content.decode("utf-8")
    except UnicodeDecodeError:
        try:
            text = content.decode("utf-8-sig")
        except UnicodeDecodeError:
            raise HTTPException(status_code=422, detail="File must be UTF-8 text.")
    text = sanitize_untrusted(text, max_len=MAX_UPLOAD_BYTES)
    if not text.strip():
        raise HTTPException(status_code=422, detail="Uploaded file contains no usable text.")
    result = await voice_profile_service.create(
        name=name,
        texts=[text],
        user_id=owner,
        workspace_id="default",
    )
    return VoiceProfileRead(
        id=result.id,
        name=result.name,
        user_id=result.user_id,
        workspace_id=result.workspace_id,
        source=result.source,
        chunk_count=result.chunk_count,
        created_at=None,
    )


@router.delete("/{profile_id}", status_code=204)
async def delete_voice_profile(profile_id: str, owner: str = Depends(verify_api_key)) -> Response:
    profile = await voice_profile_service.get(profile_id)
    if profile is None:
        raise HTTPException(status_code=404, detail="Voice profile not found")
    if profile.user_id != owner:
        raise HTTPException(status_code=403, detail="Voice profile belongs to another user")
    await voice_profile_service.delete(profile_id, user_id=profile.user_id, workspace_id=profile.workspace_id)
    return Response(status_code=204)
