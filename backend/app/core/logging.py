import logging
import re
import sys
from typing import Any
from backend.app.core.config import settings

# Sensitive patterns to sanitize from logs
SENSITIVE_PATTERNS = [
    re.compile(r"(api[_-]?key|secret|password|token)\s*[:=]\s*['\"]?([a-zA-Z0-9_\-\.]{8,})['\"]?", re.IGNORECASE),
    re.compile(r"(Bearer\s+)([a-zA-Z0-9_\-\.]{15,})", re.IGNORECASE),
]


class SecretSanitizingFormatter(logging.Formatter):
    """Custom logging formatter that masks API keys, secrets, and auth tokens."""

    def format(self, record: logging.LogRecord) -> str:
        original = super().format(record)
        sanitized = original
        for pattern in SENSITIVE_PATTERNS:
            sanitized = pattern.sub(r"\1=***REDACTED***", sanitized)
        return sanitized


def setup_logger(name: str = "farmer_ai") -> logging.Logger:
    logger = logging.getLogger(name)
    level = getattr(logging, settings.LOG_LEVEL.upper(), logging.INFO)
    logger.setLevel(level)

    if not logger.handlers:
        handler = logging.StreamHandler(sys.stdout)
        handler.setLevel(level)
        formatter = SecretSanitizingFormatter(
            fmt="%(asctime)s | %(levelname)-8s | %(name)s:%(funcName)s:%(lineno)d - %(message)s",
            datefmt="%Y-%m-%d %H:%M:%S",
        )
        handler.setFormatter(formatter)
        logger.addHandler(handler)

    logger.propagate = False
    return logger


logger = setup_logger()
