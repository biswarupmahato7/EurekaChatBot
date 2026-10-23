"""
backend/app/llm/exceptions.py
=============================
Sanitized exceptions for LLM interactions.
Ensures provider internal structures, API keys, or raw payloads are never leaked.
"""
from __future__ import annotations

from typing import Optional


class LLMError(Exception):
    """Base exception for all LLM client failures."""

    def __init__(self, message: str, sanitized_details: Optional[str] = None):
        super().__init__(message)
        self.message = message
        self.sanitized_details = sanitized_details

    def __str__(self) -> str:
        if self.sanitized_details:
            return f"{self.message} ({self.sanitized_details})"
        return self.message


class LLMConfigError(LLMError):
    """Raised when LLM client is misconfigured (e.g. missing API key or model name)."""


class LLMTimeoutError(LLMError):
    """Raised when a request to the LLM provider times out."""


class LLMRateLimitError(LLMError):
    """Raised when the LLM provider responds with 429 Too Many Requests."""

    def __init__(self, message: str, retry_after: Optional[float] = None):
        super().__init__(message, sanitized_details=f"retry_after={retry_after}s" if retry_after else None)
        self.retry_after = retry_after


class LLMUnavailableError(LLMError):
    """Raised when the LLM provider is down, experiencing internal server errors, or unreachable."""


class LLMBadRequestError(LLMError):
    """Raised when request payload or parameters are rejected by the provider."""


class LLMResponseMalformedError(LLMError):
    """Raised when the provider output could not be parsed into expected text."""
