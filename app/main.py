import asyncio
import logging
import os
from contextlib import asynccontextmanager
from typing import AsyncIterator

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.api.billing import router as billing_router
from app.api.competitors import router as competitors_router
from app.api.dub import router as dub_router
from app.api.feedback import router as feedback_router
from app.api.hooks import router as hooks_router
from app.api.jobs import router as jobs_router
from app.api.plans import router as plans_router
from app.api.prompt_registry import router as prompt_registry_router
from app.api.scripts import router as scripts_router
from app.api.storyboard import router as storyboard_router
from app.api.tts import router as tts_router
from app.api.trends import router as trends_router
from app.api.voice_profiles import router as voice_profiles_router
from app.api.workspaces import router as workspaces_router
from app.api.youtube import router as youtube_router
from app.api.webhooks import router as webhooks_router
from app.core.config import settings
from app.core.logging import setup_logging
from app.models.db import ScriptJob, SQLModel, async_session, engine
from sqlalchemy import select
from app.services.trends import trend_service
from app.services.vector_store import get_vector_store

logger = logging.getLogger("youtube_script_generator")

BANNED_DEFAULT = "dev-insecure-key-change-me"


async def _trend_scheduler() -> None:
    service = trend_service
    while True:
        await asyncio.sleep(settings.TREND_CACHE_HOURS * 3600)
        try:
            trends = await service.get_trends(settings.DEFAULT_TREND_NICHE)
            logger.info("trend refresh completed", extra={"niche": settings.DEFAULT_TREND_NICHE, "count": len(trends)})
        except Exception:  # noqa: BLE001
            logger.exception("trend refresh failed")


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    setup_logging()
    # Optional Sentry
    if settings.SENTRY_DSN:
        try:
            import sentry_sdk

            sentry_sdk.init(dsn=settings.SENTRY_DSN, traces_sample_rate=0.1, environment=settings.APP_ENV)
            logger.info("sentry initialized")
        except Exception:
            logger.exception("failed to initialize sentry (continuing without it)")
    os.makedirs("data", exist_ok=True)
    async with engine.begin() as conn:
        await conn.run_sync(SQLModel.metadata.create_all)
    # Mark stale in-flight jobs as failed so they can be retried cleanly (POST /v1/scripts/{id}/retry)
    async with async_session() as session:
        try:
            result = await session.execute(select(ScriptJob).where(ScriptJob.status.in_(("pending", "running"))))
            orphans = list(result.scalars().all())
            for row in orphans:
                row.status = "failed"
                row.error = "Server restarted during processing; retry via POST /v1/scripts/{id}/retry"
            if orphans:
                await session.commit()
                logger.warning("marked %d orphaned jobs as failed on startup", len(orphans))
        except Exception:
            logger.exception("failed to clean orphaned jobs")
    app.state.trend_task = asyncio.create_task(_trend_scheduler())
    yield
    task = getattr(app.state, "trend_task", None)
    if task is not None:
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass
    await engine.dispose()


def _validate_runtime_configuration() -> None:
    """Fail fast in production if the environment is unsafe."""
    env = (settings.APP_ENV or "development").strip().lower()
    key = (settings.API_KEY or "").strip()
    if env != "production":
        return
    if (
        not key
        or key == BANNED_DEFAULT
        or len(key) < 32
    ):
        raise RuntimeError(
            "Refuse to start: APP_ENV=production requires API_KEY set to at least 32 random characters. "
            "Generate one with `python scripts/generate_secret.py`."
        )
    if "*" in (settings.ALLOWED_ORIGINS or ""):
        raise RuntimeError("Refuse to start: ALLOWED_ORIGINS cannot contain '*' in production.")


def _build_cors_origins() -> list[str]:
    origins = [o.strip() for o in (settings.ALLOWED_ORIGINS or "").split(",") if o.strip()]
    env = (settings.APP_ENV or "development").strip().lower()
    if env == "production" and "*" in origins:
        raise RuntimeError("Refuse to start: ALLOWED_ORIGINS cannot contain '*' in production.")
    return origins or ["http://localhost:3000", "http://127.0.0.1:3000"]


_validate_runtime_configuration()

app = FastAPI(
    title="YouTube Script Generator",
    description="Multi-agent YouTube script generation pipeline (Outline -> Hook -> Writer -> Critic).",
    version="0.1.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=_build_cors_origins(),
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
    allow_headers=["Content-Type", "X-API-Key", "Authorization", "Accept"],
)


app.include_router(scripts_router, prefix="/v1")
app.include_router(plans_router, prefix="/v1")
app.include_router(trends_router, prefix="/v1")
app.include_router(competitors_router, prefix="/v1")
app.include_router(hooks_router, prefix="/v1")
app.include_router(dub_router, prefix="/v1")
app.include_router(tts_router, prefix="/v1")
app.include_router(storyboard_router, prefix="/v1")
app.include_router(workspaces_router, prefix="/v1")
app.include_router(billing_router, prefix="/v1")
app.include_router(youtube_router, prefix="/v1")
app.include_router(voice_profiles_router, prefix="/v1")
app.include_router(feedback_router, prefix="/v1")
app.include_router(webhooks_router, prefix="/v1")
app.include_router(jobs_router, prefix="/v1")
app.include_router(prompt_registry_router, prefix="/v1")

MAX_BODY_BYTES = 6 * 1024 * 1024  # 6 MB overall (voice-profile imports)


@app.middleware("http")
async def security_headers_and_size_limit(request, call_next):
    content_length = request.headers.get("content-length")
    if content_length:
        try:
            if int(content_length) > MAX_BODY_BYTES:
                return JSONResponse(status_code=413, content={"detail": "Request body too large"})
        except ValueError:
            return JSONResponse(status_code=400, content={"detail": "Invalid Content-Length header"})
    response = await call_next(request)
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["Referrer-Policy"] = "no-referrer"
    response.headers["Permissions-Policy"] = "camera=(), microphone=(), geolocation=()"
    response.headers["Content-Security-Policy"] = "default-src 'none'; frame-ancestors 'none'; base-uri 'none'"
    if (settings.APP_ENV or "development").strip().lower() == "production":
        response.headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains"
    return response


@app.get("/health")
async def health() -> dict:
    return {"status": "ok", "service": "youtube-script-generator"}


@app.get("/health/vector")
async def health_vector() -> dict:
    """Vector store health: ok/error, provider (qdrant|memory), collection status. Never exposes URL or API key."""
    from app.services.embeddings import get_embeddings_service

    store = get_vector_store()
    report: dict = {"status": "ok", "provider": store.provider, "collection": store.collection_name, "embedding_model": settings.EMBEDDING_MODEL}
    try:
        try:
            dim = await get_embeddings_service().dimension()
            dimension_source = "probe"
        except Exception as exc:
            logger.warning("embedding dimension probe failed; using fallback dimension", extra={"error": str(exc)[:150]})
            dim = 3072  # current Gemini embedding default (both gemini-embedding-001 and -2); overridden at first real upsert
            dimension_source = "fallback"
        await store.ensure_collection(dim)
        status = await store.status()
        report.update(status)
        report["dimension"] = dim
        report["dimension_source"] = dimension_source
        ok = status.get("collection_status") == "created"
        report["status"] = "ok" if ok else "error"
        return report
    except Exception as exc:
        logger.warning("vector store health check failed", extra={"error": str(exc)[:200]})
        report["status"] = "error"
        try:
            report.update(await store.status())
        except Exception:
            report["collection_status"] = "error"
        report["detail"] = str(exc)[:150]
        return report


@app.get("/")
async def root() -> dict:
    return {
        "service": "youtube-script-generator",
        "status": "ok",
        "version": "0.1.0",
        "health": "/health",
        "docs": "/docs",
    }


@app.get("/v1/models")
async def list_models() -> dict:
    """OpenAI-compatible model listing (read-only, unauthenticated like /health)."""
    data: list[dict] = []

    def add(model: str, owner: str) -> None:
        if model and not any(item["id"] == model for item in data):
            data.append({"id": model, "object": "model", "created": 0, "owned_by": owner})

    provider = (settings.LLM_PROVIDER or "gemini").strip().lower()
    if provider == "gemini":
        for model in [settings.GEMINI_MODEL_FAST, settings.GEMINI_MODEL_WRITER]:
            add(model, "google")
        for model in settings.GEMINI_MODEL_FALLBACKS.split(","):
            add(model.strip(), "google")
        if (settings.GROQ_API_KEY or "").strip():
            add(settings.GROQ_MODEL, "groq")
    else:
        add(settings.LLM_OUTLINE_MODEL, "anthropic")
        add(settings.LLM_CRITIC_MODEL, "anthropic")
        add(settings.LLM_WRITER_MODEL, "anthropic")
    return {"object": "list", "data": data}
