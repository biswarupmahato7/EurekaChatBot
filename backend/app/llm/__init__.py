"""
backend/app/llm/__init__.py
===========================
LLM client adapters and exceptions.
"""
from backend.app.llm.exceptions import (
    LLMBadRequestError,
    LLMConfigError,
    LLMError,
    LLMRateLimitError,
    LLMResponseMalformedError,
    LLMTimeoutError,
    LLMUnavailableError,
)
from backend.app.llm.groq_client import GroqClient
from backend.app.llm.openai_client import OpenAIClient

__all__ = [
    "OpenAIClient",
    "GroqClient",
    "LLMError",
    "LLMConfigError",
    "LLMTimeoutError",
    "LLMRateLimitError",
    "LLMUnavailableError",
    "LLMBadRequestError",
    "LLMResponseMalformedError",
]
