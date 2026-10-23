"""
backend/app/llm/groq_client.py
==============================
Dedicated Groq LLM client adapter with timeout, bounded retries, and sanitized error mapping.
Follows Problem Statement §10 and Architecture §6.4.
"""
from __future__ import annotations

import asyncio
import logging
import time
from typing import Any, Optional

import groq
from groq import Groq, AsyncGroq

from backend.app.llm.exceptions import (
    LLMBadRequestError,
    LLMConfigError,
    LLMError,
    LLMRateLimitError,
    LLMResponseMalformedError,
    LLMTimeoutError,
    LLMUnavailableError,
)

logger = logging.getLogger(__name__)


class GroqClient:
    """
    Isolated client for interacting with Groq LLM API.
    
    Features:
    - Configurable model, timeouts, and maximum retry counts.
    - Transparent bounded exponential backoff and Retry-After handling.
    - Complete isolation of credentials: keys are never logged or exposed in exceptions.
    - Mapping of provider exceptions to sanitized internal LLMError hierarchy.
    """

    def __init__(
        self,
        api_key: Optional[str] = None,
        model: Optional[str] = None,
        timeout_seconds: float = 30.0,
        max_retries: int = 2,
        max_output_tokens: int = 1024,
    ) -> None:
        self.api_key = api_key.strip() if api_key and api_key.strip() else None
        self.model = model.strip() if model and model.strip() else None
        self.timeout_seconds = max(1.0, float(timeout_seconds))
        self.max_retries = max(0, min(int(max_retries), 2))  # At most 2 retries per requirement
        self.max_output_tokens = max(16, int(max_output_tokens))

        self._sync_client: Optional[Groq] = None
        self._async_client: Optional[AsyncGroq] = None

    @property
    def is_configured(self) -> bool:
        """True if both API key and model name are set."""
        return bool(self.api_key and self.model)

    def _get_sync_client(self) -> Groq:
        if not self.is_configured:
            raise LLMConfigError("Groq client is not fully configured (missing API key or model).")
        if self._sync_client is None:
            # We disable SDK auto-retries so our custom bounded retry handler controls retry behavior
            self._sync_client = Groq(
                api_key=self.api_key,
                timeout=self.timeout_seconds,
                max_retries=0,
            )
        return self._sync_client

    def _get_async_client(self) -> AsyncGroq:
        if not self.is_configured:
            raise LLMConfigError("Groq client is not fully configured (missing API key or model).")
        if self._async_client is None:
            self._async_client = AsyncGroq(
                api_key=self.api_key,
                timeout=self.timeout_seconds,
                max_retries=0,
            )
        return self._async_client

    def generate(
        self,
        messages: list[dict[str, str]],
        temperature: float = 0.1,
        max_tokens: Optional[int] = None,
    ) -> str:
        """
        Synchronously generate a completion from Groq with bounded retries.
        """
        if not self.is_configured:
            raise LLMConfigError("Groq API key or model is not configured.")

        client = self._get_sync_client()
        tokens = min(max_tokens or self.max_output_tokens, self.max_output_tokens)
        attempts = 1 + self.max_retries

        last_error: Optional[Exception] = None
        for attempt in range(1, attempts + 1):
            try:
                t0 = time.perf_counter()
                response = client.chat.completions.create(
                    model=self.model,  # type: ignore[arg-type]
                    messages=messages,  # type: ignore[arg-type]
                    temperature=temperature,
                    max_tokens=tokens,
                )
                duration = time.perf_counter() - t0
                logger.info(
                    "Groq completion succeeded on attempt %d/%d (model=%s, duration=%.3fs)",
                    attempt,
                    attempts,
                    self.model,
                    duration,
                )
                return self._extract_content(response)

            except (groq.APITimeoutError,) as exc:
                last_error = LLMTimeoutError(f"Groq request timed out after {self.timeout_seconds}s")
                if attempt < attempts:
                    backoff = min(0.5 * (2 ** (attempt - 1)), 2.0)
                    logger.warning("Groq timeout on attempt %d/%d; retrying in %.2fs", attempt, attempts, backoff)
                    time.sleep(backoff)
                    continue
                raise last_error from None

            except groq.RateLimitError as exc:
                retry_after = self._parse_retry_after(exc)
                last_error = LLMRateLimitError("Groq rate limit exceeded", retry_after=retry_after)
                if attempt < attempts and (retry_after is None or retry_after <= 3.0):
                    delay = retry_after if retry_after is not None else 1.0
                    logger.warning("Groq 429 on attempt %d/%d; retrying in %.2fs", attempt, attempts, delay)
                    time.sleep(delay)
                    continue
                raise last_error from None

            except (groq.InternalServerError, groq.APIConnectionError) as exc:
                last_error = LLMUnavailableError(f"Groq service unavailable: {type(exc).__name__}")
                if attempt < attempts:
                    backoff = min(0.5 * (2 ** (attempt - 1)), 2.0)
                    logger.warning("Groq transient error on attempt %d/%d; retrying in %.2fs", attempt, attempts, backoff)
                    time.sleep(backoff)
                    continue
                raise last_error from None

            except (groq.AuthenticationError, groq.PermissionDeniedError) as exc:
                logger.error("Groq authentication failure. Invalid API credentials.")
                raise LLMConfigError("Groq authentication failed. Please verify GROQ_API_KEY.") from None

            except (groq.BadRequestError, groq.NotFoundError) as exc:
                logger.error("Groq bad request or model not found: %s", type(exc).__name__)
                raise LLMBadRequestError("Groq rejected parameters or model was not found.") from None

            except groq.GroqError as exc:
                logger.error("Unexpected Groq error: %s", type(exc).__name__)
                raise LLMError(f"Groq API error: {type(exc).__name__}") from None

            except LLMError:
                raise

            except Exception as exc:
                logger.error("Unexpected error during LLM generation: %s", type(exc).__name__)
                raise LLMError(f"Unexpected generation failure: {type(exc).__name__}") from None

        if last_error:
            raise last_error
        raise LLMUnavailableError("Groq generation failed after all attempts.")

    async def agenerate(
        self,
        messages: list[dict[str, str]],
        temperature: float = 0.1,
        max_tokens: Optional[int] = None,
    ) -> str:
        """
        Asynchronously generate a completion from Groq with bounded retries.
        """
        if not self.is_configured:
            raise LLMConfigError("Groq API key or model is not configured.")

        client = self._get_async_client()
        tokens = min(max_tokens or self.max_output_tokens, self.max_output_tokens)
        attempts = 1 + self.max_retries

        last_error: Optional[Exception] = None
        for attempt in range(1, attempts + 1):
            try:
                t0 = time.perf_counter()
                response = await client.chat.completions.create(
                    model=self.model,  # type: ignore[arg-type]
                    messages=messages,  # type: ignore[arg-type]
                    temperature=temperature,
                    max_tokens=tokens,
                )
                duration = time.perf_counter() - t0
                logger.info(
                    "Async Groq completion succeeded on attempt %d/%d (model=%s, duration=%.3fs)",
                    attempt,
                    attempts,
                    self.model,
                    duration,
                )
                return self._extract_content(response)

            except groq.APITimeoutError:
                last_error = LLMTimeoutError(f"Groq request timed out after {self.timeout_seconds}s")
                if attempt < attempts:
                    backoff = min(0.5 * (2 ** (attempt - 1)), 2.0)
                    logger.warning("Groq timeout on attempt %d/%d; retrying in %.2fs", attempt, attempts, backoff)
                    await asyncio.sleep(backoff)
                    continue
                raise last_error from None

            except groq.RateLimitError as exc:
                retry_after = self._parse_retry_after(exc)
                last_error = LLMRateLimitError("Groq rate limit exceeded", retry_after=retry_after)
                if attempt < attempts and (retry_after is None or retry_after <= 3.0):
                    delay = retry_after if retry_after is not None else 1.0
                    logger.warning("Groq 429 on attempt %d/%d; retrying in %.2fs", attempt, attempts, delay)
                    await asyncio.sleep(delay)
                    continue
                raise last_error from None

            except (groq.InternalServerError, groq.APIConnectionError) as exc:
                last_error = LLMUnavailableError(f"Groq service unavailable: {type(exc).__name__}")
                if attempt < attempts:
                    backoff = min(0.5 * (2 ** (attempt - 1)), 2.0)
                    logger.warning("Groq transient error on attempt %d/%d; retrying in %.2fs", attempt, attempts, backoff)
                    await asyncio.sleep(backoff)
                    continue
                raise last_error from None

            except (groq.AuthenticationError, groq.PermissionDeniedError):
                logger.error("Groq authentication failure. Invalid API credentials.")
                raise LLMConfigError("Groq authentication failed. Please verify GROQ_API_KEY.") from None

            except (groq.BadRequestError, groq.NotFoundError):
                logger.error("Groq bad request or model not found.")
                raise LLMBadRequestError("Groq rejected parameters or model was not found.") from None

            except groq.GroqError as exc:
                logger.error("Unexpected Groq error: %s", type(exc).__name__)
                raise LLMError(f"Groq API error: {type(exc).__name__}") from None

            except LLMError:
                raise

            except Exception as exc:
                logger.error("Unexpected error during async generation: %s", type(exc).__name__)
                raise LLMError(f"Unexpected generation failure: {type(exc).__name__}") from None

        if last_error:
            raise last_error
        raise LLMUnavailableError("Groq generation failed after all attempts.")

    @staticmethod
    def _extract_content(response: Any) -> str:
        """Safely extract generated content from provider response."""
        if not response or not hasattr(response, "choices") or not response.choices:
            raise LLMResponseMalformedError("Groq returned empty choices list.")

        first_choice = response.choices[0]
        if not hasattr(first_choice, "message") or not first_choice.message:
            raise LLMResponseMalformedError("Groq choice missing message object.")

        content = getattr(first_choice.message, "content", None)
        if content is None:
            raise LLMResponseMalformedError("Groq message content is null.")

        return str(content).strip()

    @staticmethod
    def _parse_retry_after(exc: Any) -> Optional[float]:
        """Attempt to extract numeric retry-after from error headers if available."""
        try:
            if hasattr(exc, "response") and exc.response is not None:
                headers = getattr(exc.response, "headers", {})
                ra = headers.get("retry-after")
                if ra:
                    return float(ra)
        except Exception:
            pass
        return None
