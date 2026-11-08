import json
import logging
import sys

from app.core.config import settings
from app.services.security_utils import redact

logger = logging.getLogger("youtube_script_generator")


class SecretRedactionFilter(logging.Filter):
    """Redact secrets/tokens from every log record before it is emitted."""

    def filter(self, record: logging.LogRecord) -> bool:
        record.msg = redact(record.getMessage())
        record.args = ()
        if record.exc_info:
            record.exc_text = redact(str(record.exc_info[1]))
        return True


class JsonLogFormatter(logging.Formatter):
    """Minimal JSON line formatter for structured logs."""

    def format(self, record: logging.LogRecord) -> str:
        payload: dict = {
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
            "timestamp": record.created,
        }
        if record.exc_info:
            payload["exception"] = str(record.exc_info[1])
        return json.dumps(payload)


def setup_logging() -> None:
    level = getattr(logging, str(settings.LOG_LEVEL).upper(), logging.INFO)
    root = logging.getLogger()
    root.setLevel(level)
    if not root.handlers:
        handler = logging.StreamHandler(sys.stdout)
        handler.setFormatter(JsonLogFormatter())
        handler.addFilter(SecretRedactionFilter())
        root.addHandler(handler)


def get_logger(name: str = "youtube_script_generator") -> logging.Logger:
    return logging.getLogger(name)
