from __future__ import annotations

import logging
import os
import sys

_NOISY_GET_PATHS = (
    "GET /api/system/status",
    "GET /api/characters",
    "GET /api/worlds",
    "GET /api/chats",
    "GET /api/workflows",
    "GET /api/gallery",
    "GET /media/generated/",
)


class _QuietPollingAccessFilter(logging.Filter):
    """Suppresses routine 200/304 GET polling requests from uvicorn.access so action logs stay readable."""

    def filter(self, record: logging.LogRecord) -> bool:
        msg = record.getMessage()
        if any(p in msg for p in _NOISY_GET_PATHS) and (" 200 " in msg or " 304 " in msg):
            return False
        return True


class _JsonCloudFormatter(logging.Formatter):
    """Structured JSON formatter compatible with Google Cloud Logging."""

    def format(self, record: logging.LogRecord) -> str:
        import json

        payload: dict[str, object] = {
            "severity": record.levelname,
            "message": record.getMessage(),
            "logger": record.name,
        }
        service = os.environ.get("K_SERVICE")
        if service:
            payload["service"] = service
        if record.exc_info:
            payload["exc_info"] = self.formatException(record.exc_info)
        return json.dumps(payload, ensure_ascii=False)


def setup_hivemind_logger(level_name: str | None = None) -> logging.Logger:
    logger = logging.getLogger("hivemind")
    resolved_name = (level_name or os.environ.get("HIVEMIND_LOG_LEVEL", "INFO")).upper()
    level = getattr(logging, resolved_name, logging.INFO)
    logger.setLevel(level)

    if not logger.handlers:
        handler = logging.StreamHandler(sys.stdout)
        use_json = (
            os.environ.get("LOG_FORMAT", "").strip().lower() == "json"
            or bool(os.environ.get("K_SERVICE"))
        )
        if use_json:
            formatter: logging.Formatter = _JsonCloudFormatter()
        else:
            formatter = logging.Formatter(
                fmt="\033[36m%(asctime)s\033[0m [\033[1;33mHIVEMIND\033[0m] %(message)s",
                datefmt="%H:%M:%S",
            )
        handler.setFormatter(formatter)
        logger.addHandler(handler)
        logger.propagate = False

    # Attach polling filter to uvicorn.access logger
    access_logger = logging.getLogger("uvicorn.access")
    if not any(isinstance(f, _QuietPollingAccessFilter) for f in access_logger.filters):
        access_logger.addFilter(_QuietPollingAccessFilter())

    return logger


def set_hivemind_log_level(level_name: str) -> None:
    logger = setup_hivemind_logger(level_name)
    resolved = getattr(logging, level_name.upper(), logging.INFO)
    logger.setLevel(resolved)


logger = setup_hivemind_logger()
