from __future__ import annotations

import logging
from typing import Any


def get_logger(name: str = "platform") -> logging.Logger:
    """Return a configured logger."""

    logger = logging.getLogger(name)
    if not logger.handlers:
        handler = logging.StreamHandler()
        formatter = logging.Formatter("%(asctime)s %(levelname)s [session_id=%(session_id)s] %(message)s")
        handler.setFormatter(formatter)
        logger.addHandler(handler)
        logger.propagate = False
    return logger


def log_with_correlation(
    logger: logging.Logger,
    level: int,
    message: str,
    *,
    session_id: str | None = None,
    **kwargs: Any,
) -> None:
    """Log a message including session correlation metadata."""

    extra = {"session_id": session_id or "-", **kwargs}
    logger.log(level, message, extra=extra)


__all__ = ["get_logger", "log_with_correlation"]
