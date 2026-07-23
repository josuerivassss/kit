"""Structured logging configuration.

Replaces the ad-hoc `print()` statements used throughout the v1 codebase
with structured, leveled, machine-parsable logs (JSON in production,
human-readable in local development), tagged with shard/cluster context.
"""
from __future__ import annotations

import logging
import sys

import structlog

from bcommie.config import Settings


def configure_logging(settings: Settings) -> None:
    """Configure stdlib logging + structlog for the whole process."""
    logging.basicConfig(
        format="%(message)s",
        stream=sys.stdout,
        level=getattr(logging, settings.log_level.upper(), logging.INFO),
    )
    # Third-party HTTP clients (aiohttp, httpx, and whatever curl_cffi/primp
    # backend ddgs uses under the hood) log every single request at INFO/DEBUG
    # by default. Since they propagate to the root logger configured above,
    # they'd otherwise flood output with every outbound call (including full
    # query strings -- a privacy concern for something like image search).
    # Keep only warnings/errors from these; our own loggers are unaffected.
    for noisy_logger in ("aiohttp", "aiohttp.client", "httpx", "httpcore", "curl_cffi", "primp"):
        logging.getLogger(noisy_logger).setLevel(logging.WARNING)

    shared_processors: list[structlog.types.Processor] = [
        structlog.contextvars.merge_contextvars,
        structlog.stdlib.add_log_level,
        structlog.stdlib.add_logger_name,
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.processors.StackInfoRenderer(),
        structlog.processors.format_exc_info,
    ]

    renderer: structlog.types.Processor = (
        structlog.processors.JSONRenderer()
        if settings.log_format == "json"
        else structlog.dev.ConsoleRenderer()
    )

    structlog.configure(
        processors=[*shared_processors, renderer],
        wrapper_class=structlog.make_filtering_bound_logger(
            getattr(logging, settings.log_level.upper(), logging.INFO)
        ),
        context_class=dict,
         logger_factory=structlog.stdlib.LoggerFactory(),
        cache_logger_on_first_use=True,
    )


def get_logger(name: str) -> structlog.stdlib.BoundLogger:
    """Return a bound structlog logger, conventionally called with __name__."""
    return structlog.get_logger(name)
