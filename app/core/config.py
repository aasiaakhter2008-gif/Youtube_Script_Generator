from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
    )

    # LLM provider (gemini | anthropic). Zero-cost default: Gemini free tier.
    LLM_PROVIDER: str = "gemini"
    ANTHROPIC_API_KEY: str = ""
    ANTHROPIC_BASE_URL: str = "https://api.anthropic.com"
    LLM_OUTLINE_MODEL: str = "claude-3-haiku-20240307"
    LLM_CRITIC_MODEL: str = "claude-3-haiku-20240307"
    LLM_WRITER_MODEL: str = "claude-sonnet-4-20250514"
    GEMINI_API_KEY: str = ""
    GEMINI_MODEL_FAST: str = "gemini-3.8-flash"
    GEMINI_MODEL_WRITER: str = "gemini-3.1-pro-preview"
    # Ordered Gemini model chain used as fallback when the primary model is overloaded (503) or rate limited (429)
    GEMINI_MODEL_FALLBACKS: str = "gemini-3.6-flash,gemini-3.5-flash-lite,gemini-3.1-flash-lite"
    # Optional last-resort provider (Groq, OpenAI-compatible). Skipped silently when GROQ_API_KEY is empty.
    # Groq's current free flagship (Nov 2026) is gpt-oss-120b; 20b is the lighter free option.
    GROQ_API_KEY: str = ""
    GROQ_MODEL: str = "openai/gpt-oss-120b"
    # Free-tier friendly defaults: limited RPM/concurrency; response cache TTL avoids duplicate spend while debugging
    LLM_REQUESTS_PER_MINUTE: int = 8
    LLM_MAX_CONCURRENCY: int = 2
    LLM_CACHE_TTL_SECONDS: int = 3600
    # Per-request timeout for a single model call. Free-tier models can stall; a timeout
    # makes the fallback chain move to the next model instead of hanging the pipeline.
    GEMINI_REQUEST_TIMEOUT_SECONDS: float = 90.0

    # Eval gate. Free-tier-only chains run in "report mode" (print score, warn, exit 0).
    # EVAL_MODE: auto (report when free-tier only) | report (never fail) | enforce (always fail below threshold)
    EVAL_MIN_SCORE: float = 7.0
    EVAL_MODE: str = "auto"

    # Per-user daily generation quota (0 = unlimited). Counts generations started since 00:00 UTC.
    GENERATION_DAILY_LIMIT_PER_USER: int = 20

    # Qdrant vector store. Leave QDRANT_URL/QDRANT_API_KEY empty to use the in-memory fallback.
    # Get them in Qdrant Cloud -> Clusters -> your cluster -> API Keys (or http://localhost:6333 for self-hosted).
    QDRANT_URL: str = ""
    QDRANT_API_KEY: str = ""
    QDRANT_COLLECTION_PREFIX: str = "ysg"
    # Current Gemini text embedding model (gemini-embedding-2, stable since April 2026; 3072-dim default, 8192-token limit).
    EMBEDDING_MODEL: str = "gemini-embedding-2"

    # Generation
    TEMPERATURE: float = 0.7
    MAX_REVISIONS: int = 2
    CRITIC_PASS_THRESHOLD: float = 8.0
    TARGET_WPM: int = 140
    AGENT_TIMEOUT_SECONDS: float = 90.0

    # Offline eval gate (Phase 4): fail CI if average judge score drops below threshold
    EVAL_THRESHOLD: float = 7.0

    # Error tracking: optional Sentry DSN (empty = disabled)
    SENTRY_DSN: str = ""

    # Runtime environment: production | development
    APP_ENV: str = "development"

    # CORS: comma-separated allowed origins (never "*" in production)
    ALLOWED_ORIGINS: str = "http://localhost:3000,http://127.0.0.1:3000"

    # API key auth + basic rate limiting (JWT comes in Phase 2). No default: must be provided.
    API_KEY: str = ""
    RATE_LIMIT_PER_MINUTE: int = 10
    RATE_LIMIT_WINDOW_SECONDS: int = 60

    # Observability / storage
    LOG_LEVEL: str = "INFO"
    DATABASE_URL: str = "sqlite+aiosqlite:///./data/youtube_script_generator.db"
    DEFAULT_TREND_NICHE: str = "technology"
    TREND_CACHE_HOURS: int = 24

    # TTS (Phase 3 item 6). Default is the free Edge TTS provider.
    ELEVENLABS_API_KEY: str = ""
    TTS_PROVIDER: str = "edge"
    TTS_VOICE: str = "en-US-AriaNeural"

    # Billing (Phase 4) – optional; absence of key returns 501 "not configured"
    STRIPE_API_KEY: str = ""

    # Translation / dubbing (Phase 3 item 5)
    SUPPORTED_LANGUAGES: str = "English,Urdu,Roman Urdu,Hindi,Arabic,Spanish"


settings = Settings()
