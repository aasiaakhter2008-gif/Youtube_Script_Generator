"""Security helpers that avoid logging secrets and treat external/fetched text as untrusted.

Nothing in here ever logs full prompts, user content, or API keys.
"""

import logging
import os
import re

logger = logging.getLogger("youtube_script_generator")

MAX_UNTRUSTED_LEN = 8000
MAX_UPLOAD_BYTES = 5 * 1024 * 1024  # 5 MB
ALLOWED_UPLOAD_EXTENSIONS = {".txt", ".md"}

# Patterns for well-known secret / token shapes that should never appear in logs.
_SECRET_PATTERNS = [
    re.compile(r"AIza[0-9A-Za-z_\-]{20,}"),
    re.compile(r"sk-[A-Za-z0-9_\-]{16,}"),
    re.compile(r"ghp_[0-9A-Za-z]{20,}"),
    re.compile(r"gho_[0-9A-Za-z]{20,}"),
    re.compile(r"ya29\.[0-9A-Za-z_\-\.]{20,}"),
    re.compile(r"xi-api-key[\"']?[:=]\s*[\"']?[0-9A-Za-z_\-]{16,}", re.IGNORECASE),
    re.compile(r"api[_-]?key[\"']?[:=]\s*[\"']?[0-9A-Za-z_\-]{16,}", re.IGNORECASE),
    re.compile(r"gl-[0-9a-z]{16,}", re.IGNORECASE),
    re.compile(r"(?:glc_|sk_)[0-9A-Za-z_\-]{16,}"),
    re.compile(r"eyJ[0-9A-Za-z_\-]{10,}\.[0-9A-Za-z_\-]{10,}\.[0-9A-Za-z_\-]{10,}"),
]

_INJECTION_PATTERNS = [
    re.compile(r"(ignore|disregard|forget)\s+(all|every|any|the)?\s*(previous|prior|above|earlier)\s+(instructions?|prompts?|rules?|context)", re.IGNORECASE),
    re.compile(r"you are now\s+(a|an|the)\s", re.IGNORECASE),
    re.compile(r"system\s*prompt", re.IGNORECASE),
    re.compile(r"<\s*/?\s*system\s*>", re.IGNORECASE),
    re.compile(r"reveal\s+(your|the)\s+(system|hidden|secret|original)", re.IGNORECASE),
    re.compile(r"(print|repeat|output)\s+(your|the)\s+(instructions?|system prompt|rules?)", re.IGNORECASE),
    re.compile(r"new\s+(system|primary|top)\s+(instruction|prompt|directive)", re.IGNORECASE),
]


def redact(value: object) -> str:
    """Redact secret-shaped strings from text before it reaches logs or error responses."""
    text = str(value)
    for env_name in (
        "GEMINI_API_KEY",
        "ANTHROPIC_API_KEY",
        "QDRANT_API_KEY",
        "ELEVENLABS_API_KEY",
        "GROQ_API_KEY",
        "STRIPE_API_KEY",
        "LEMON_SQUEEZY_API_KEY",
        "API_KEY",
        "SECRET_KEY",
        "DATABASE_URL",
    ):
        secret = os.environ.get(env_name) or ""
        if len(secret) > 12:
            text = text.replace(secret, "[REDACTED]")
    for pattern in _SECRET_PATTERNS:
        text = pattern.sub("[REDACTED]", text)
    return text


def looks_like_prompt_injection(text: str) -> bool:
    sample = (text or "")[:4000]
    return any(pattern.search(sample) for pattern in _INJECTION_PATTERNS)


def sanitize_untrusted(text: str, *, max_len: int = MAX_UNTRUSTED_LEN) -> str:
    """Strip inline markdown fences/HTML-ish artifacts and injection directives from fetched text."""
    cleaned = (text or "")[:max_len]
    cleaned = re.sub(r"```(json|bash|python|shell|text)?\s*", " ", cleaned)
    cleaned = re.sub(r"<\s*(script|style|iframe|form|input)[^>]*>.*?<\s*/\s*\1\s*>", " ", cleaned, flags=re.IGNORECASE | re.DOTALL)
    for pattern in _INJECTION_PATTERNS:
        cleaned = pattern.sub("[untrusted-content-filtered]", cleaned)
    cleaned = re.sub(r"\s{2,}", " ", cleaned).strip()
    return cleaned
