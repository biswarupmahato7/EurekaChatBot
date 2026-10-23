"""
backend/logging_config.py
=========================
Structured logging configuration for backend components.
"""
from __future__ import annotations

import logging
import sys


def setup_logging(level: str | int = "INFO") -> None:
    """Configure root logger with consistent timestamps and format."""
    if isinstance(level, int):
        log_level = level
    else:
        log_level = getattr(logging, str(level).upper(), logging.INFO)
    fmt = "%(asctime)s [%(levelname)s] %(name)s: %(message)s"
    datefmt = "%Y-%m-%dT%H:%M:%S"

    logging.basicConfig(
        level=log_level,
        format=fmt,
        datefmt=datefmt,
        handlers=[logging.StreamHandler(sys.stdout)],
        force=True,
    )
