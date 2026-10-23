"""
backend/app/schemas/errors.py
=============================
Standardized error models for API responses.
"""
from __future__ import annotations

from typing import Any, Optional

from pydantic import BaseModel, Field


class ErrorDetail(BaseModel):
    """Specific field-level or contextual error detail."""

    field: Optional[str] = None
    issue: str


class ErrorBody(BaseModel):
    """Structured error payload."""

    code: str = Field(description="Machine-readable error classification code.")
    message: str = Field(description="Human-readable sanitized error description.")
    request_id: Optional[str] = Field(default=None, description="Optional embedded request correlation ID.")
    details: list[ErrorDetail] = Field(default_factory=list)


class ErrorResponse(BaseModel):
    """Top-level error response envelope matching project conventions."""

    request_id: str = Field(description="Correlation request identifier.")
    error: ErrorBody
