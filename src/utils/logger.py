"""LabiiaLex logging utilities."""

from __future__ import annotations

import logging
from typing import Optional, Union


def setup_logger(
    name: str = "lexianalyst",
    log_level: Union[str, int] = "INFO",
    log_file: Optional[str] = None,
) -> logging.Logger:
    """
    Configure and return a logger instance.

    Args:
        name: Logger name.
        log_level: Logging level as string or int.
        log_file: Optional file path for log output.

    Returns:
        Configured logging.Logger instance.
    """
    logger = logging.getLogger(name)
    if getattr(logger, "_lexianalyst_configured", False):
        return logger

    if isinstance(log_level, str):
        resolved_level = logging.getLevelName(log_level.upper())
        if isinstance(resolved_level, str):
            resolved_level = logging.INFO
    else:
        resolved_level = int(log_level)

    logger.setLevel(resolved_level)

    formatter = logging.Formatter(
        "%(asctime)s | %(levelname)s | %(name)s | %(message)s"
    )

    stream_handler = logging.StreamHandler()
    stream_handler.setFormatter(formatter)
    logger.addHandler(stream_handler)

    if log_file:
        file_handler = logging.FileHandler(log_file, encoding="utf-8")
        file_handler.setFormatter(formatter)
        logger.addHandler(file_handler)

    logger._lexianalyst_configured = True
    return logger


def get_logger(name: str = "lexianalyst") -> logging.Logger:
    """
    Return a configured logger for LabiiaLex.

    Args:
        name: Logger name.

    Returns:
        Configured logging.Logger instance.
    """
    return setup_logger(name=name)
