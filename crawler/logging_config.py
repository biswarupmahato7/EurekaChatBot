"""
crawler/logging_config.py
=========================
Structured logging configuration for the Eureka RAG Chatbot crawler.
Call setup_logging() once at the start of any CLI entry point.
"""
from __future__ import annotations

import logging
import sys


def setup_logging(level: str = "INFO", json_format: bool = False) -> None:
    """Configure root logger with appropriate handlers and format."""
    numeric_level = getattr(logging, level.upper(), logging.INFO)

    if json_format:
        fmt = (
            '{"time": "%(asctime)s", "level": "%(levelname)s", '
            '"logger": "%(name)s", "message": "%(message)s"}'
        )
    else:
        fmt = "%(asctime)s [%(levelname)s] %(name)s: %(message)s"

    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(logging.Formatter(fmt, datefmt="%Y-%m-%dT%H:%M:%S"))

    root = logging.getLogger()
    root.setLevel(numeric_level)
    root.handlers.clear()
    root.addHandler(handler)

    # Quiet noisy third-party libraries
    logging.getLogger("urllib3").setLevel(logging.WARNING)
    logging.getLogger("requests").setLevel(logging.WARNING)
