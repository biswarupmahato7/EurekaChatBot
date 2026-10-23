"""
backend/app/llm/openai_client.py
================================
Dedicated OpenAI LLM client adapter with timeout, bounded retries, and sanitized error mapping.
Uses the official OpenAI Python SDK and supports the Responses API (with Chat Completions fallback).
Follows Problem Statement §10 and Architecture §6.4.
"""
from __future__ import annotations

import asyncio
import logging
import time
from typing import Any, Optional

import openai
from openai import AsyncOpenAI, OpenAI

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


class OpenAIClient:
    """
    Isolated client for interacting with the OpenAI API.

    Features:
    - Primary support for OpenAI Responses API, with fallback to Chat Completions.
    - Configurable model, timeouts, and maximum retry counts.
    - Bounded exponential backoff with Retry-After header parsing.
    - Strict credential isolation: keys are never logged, formatted into exceptions, or exposed.
    - Direct mapping of OpenAI provider exceptions to sanitized internal LLMError hierarchy.
    """

    def __init__(
        self,
        api_key: Optional[str] = None,
        model: Optional[str] = "gpt-4o-mini",
        timeout_seconds: float = 30.0,
        max_retries: int = 2,
        max_output_tokens: int = 1024,
    ) -> None:
        self.api_key = api_key.strip() if api_key and api_key.strip() else None
        self.model = model.strip() if model and model.strip() else None
        self.timeout_seconds = max(1.0, float(timeout_seconds))
        self.max_retries = max(0, min(int(max_retries), 5))
        # OpenAI Responses API requires max_output_tokens >= 16
        self.max_output_tokens = max(16, int(max_output_tokens))

        self._sync_client: Optional[OpenAI] = None
        self._async_client: Optional[AsyncOpenAI] = None

    def __repr__(self) -> str:
        key_status = "set" if self.api_key else "missing"
        return f"OpenAIClient(model={self.model!r}, api_key=<{key_status}>, timeout={self.timeout_seconds}s)"

    @property
    def is_configured(self) -> bool:
        """True if both API key and model name are set."""
        return bool(self.api_key and self.model)

    def _get_sync_client(self) -> OpenAI:
        if not self.is_configured:
            raise LLMConfigError("OpenAI client is not fully configured (missing API key or model).")
        if self._sync_client is None:
            # Disable SDK automatic retries so custom bounded retry handler controls retry behavior
            self._sync_client = OpenAI(
                api_key=self.api_key,
                timeout=self.timeout_seconds,
                max_retries=0,
            )
        return self._sync_client

    def _get_async_client(self) -> AsyncOpenAI:
        if not self.is_configured:
            raise LLMConfigError("OpenAI client is not fully configured (missing API key or model).")
        if self._async_client is None:
            self._async_client = AsyncOpenAI(
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
        Synchronously generate a completion from OpenAI with bounded retries.
        """
        if not self.is_configured:
            raise LLMConfigError("OpenAI API key or model is not configured.")

        client = self._get_sync_client()
        tokens = max(16, min(max_tokens or self.max_output_tokens, self.max_output_tokens))
        attempts = 1 + self.max_retries

        last_error: Optional[Exception] = None
        for attempt in range(1, attempts + 1):
            try:
                t0 = time.perf_counter()
                response = self._call_sync_api(
                    client=client,
                    messages=messages,
                    temperature=temperature,
                    max_tokens=tokens,
                )
                duration = time.perf_counter() - t0
                logger.info(
                    "OpenAI completion succeeded on attempt %d/%d (model=%s, duration=%.3fs)",
                    attempt,
                    attempts,
                    self.model,
                    duration,
                )
                return self._extract_content(response)

            except openai.APITimeoutError:
                last_error = LLMTimeoutError(f"OpenAI request timed out after {self.timeout_seconds}s")
                if attempt < attempts:
                    backoff = min(0.5 * (2 ** (attempt - 1)), 2.0)
                    logger.warning("OpenAI timeout on attempt %d/%d; retrying in %.2fs", attempt, attempts, backoff)
                    time.sleep(backoff)
                    continue
                raise last_error from None

            except openai.RateLimitError as exc:
                if self._is_quota_or_billing_error(exc):
                    logger.error("OpenAI quota or billing limit exceeded. Permanent error, aborting retries.")
                    raise LLMUnavailableError("OpenAI quota or billing limit exceeded.") from None

                retry_after = self._parse_retry_after(exc)
                last_error = LLMRateLimitError("OpenAI rate limit exceeded", retry_after=retry_after)
                if attempt < attempts and (retry_after is None or retry_after <= 3.0):
                    delay = retry_after if retry_after is not None else 1.0
                    logger.warning("OpenAI 429 on attempt %d/%d; retrying in %.2fs", attempt, attempts, delay)
                    time.sleep(delay)
                    continue
                raise last_error from None

            except (openai.InternalServerError, openai.APIConnectionError) as exc:
                last_error = LLMUnavailableError(f"OpenAI service unavailable: {type(exc).__name__}")
                if attempt < attempts:
                    backoff = min(0.5 * (2 ** (attempt - 1)), 2.0)
                    logger.warning("OpenAI transient error on attempt %d/%d; retrying in %.2fs", attempt, attempts, backoff)
                    time.sleep(backoff)
                    continue
                raise last_error from None

            except (openai.AuthenticationError, openai.PermissionDeniedError):
                logger.error("OpenAI authentication failure. Invalid API credentials.")
                raise LLMConfigError("OpenAI authentication failed. Please verify OPENAI_API_KEY.") from None

            except (openai.BadRequestError, openai.NotFoundError) as exc:
                logger.error("OpenAI bad request or model not found: %s", type(exc).__name__)
                raise LLMBadRequestError("OpenAI rejected parameters or model was not found.") from None

            except openai.OpenAIError as exc:
                logger.error("Unexpected OpenAI API error: %s", type(exc).__name__)
                raise LLMError(f"OpenAI API error: {type(exc).__name__}") from None

            except LLMError:
                raise

            except Exception as exc:
                logger.error("Unexpected error during OpenAI generation: %s", type(exc).__name__)
                raise LLMError(f"Unexpected generation failure: {type(exc).__name__}") from None

        if last_error:
            raise last_error
        raise LLMUnavailableError("OpenAI generation failed after all attempts.")

    async def agenerate(
        self,
        messages: list[dict[str, str]],
        temperature: float = 0.1,
        max_tokens: Optional[int] = None,
    ) -> str:
        """
        Asynchronously generate a completion from OpenAI with bounded retries.
        """
        if not self.is_configured:
            raise LLMConfigError("OpenAI API key or model is not configured.")

        client = self._get_async_client()
        tokens = max(16, min(max_tokens or self.max_output_tokens, self.max_output_tokens))
        attempts = 1 + self.max_retries

        last_error: Optional[Exception] = None
        for attempt in range(1, attempts + 1):
            try:
                t0 = time.perf_counter()
                response = await self._call_async_api(
                    client=client,
                    messages=messages,
                    temperature=temperature,
                    max_tokens=tokens,
                )
                duration = time.perf_counter() - t0
                logger.info(
                    "Async OpenAI completion succeeded on attempt %d/%d (model=%s, duration=%.3fs)",
                    attempt,
                    attempts,
                    self.model,
                    duration,
                )
                return self._extract_content(response)

            except openai.APITimeoutError:
                last_error = LLMTimeoutError(f"OpenAI request timed out after {self.timeout_seconds}s")
                if attempt < attempts:
                    backoff = min(0.5 * (2 ** (attempt - 1)), 2.0)
                    logger.warning("OpenAI timeout on attempt %d/%d; retrying in %.2fs", attempt, attempts, backoff)
                    await asyncio.sleep(backoff)
                    continue
                raise last_error from None

            except openai.RateLimitError as exc:
                if self._is_quota_or_billing_error(exc):
                    logger.error("OpenAI quota or billing limit exceeded. Permanent error, aborting retries.")
                    raise LLMUnavailableError("OpenAI quota or billing limit exceeded.") from None

                retry_after = self._parse_retry_after(exc)
                last_error = LLMRateLimitError("OpenAI rate limit exceeded", retry_after=retry_after)
                if attempt < attempts and (retry_after is None or retry_after <= 3.0):
                    delay = retry_after if retry_after is not None else 1.0
                    logger.warning("OpenAI 429 on attempt %d/%d; retrying in %.2fs", attempt, attempts, delay)
                    await asyncio.sleep(delay)
                    continue
                raise last_error from None

            except (openai.InternalServerError, openai.APIConnectionError) as exc:
                last_error = LLMUnavailableError(f"OpenAI service unavailable: {type(exc).__name__}")
                if attempt < attempts:
                    backoff = min(0.5 * (2 ** (attempt - 1)), 2.0)
                    logger.warning("OpenAI transient error on attempt %d/%d; retrying in %.2fs", attempt, attempts, backoff)
                    await asyncio.sleep(backoff)
                    continue
                raise last_error from None

            except (openai.AuthenticationError, openai.PermissionDeniedError):
                logger.error("OpenAI authentication failure. Invalid API credentials.")
                raise LLMConfigError("OpenAI authentication failed. Please verify OPENAI_API_KEY.") from None

            except (openai.BadRequestError, openai.NotFoundError):
                logger.error("OpenAI bad request or model not found.")
                raise LLMBadRequestError("OpenAI rejected parameters or model was not found.") from None

            except openai.OpenAIError as exc:
                logger.error("Unexpected OpenAI API error: %s", type(exc).__name__)
                raise LLMError(f"OpenAI API error: {type(exc).__name__}") from None

            except LLMError:
                raise

            except Exception as exc:
                logger.error("Unexpected error during async generation: %s", type(exc).__name__)
                raise LLMError(f"Unexpected generation failure: {type(exc).__name__}") from None

        if last_error:
            raise last_error
        raise LLMUnavailableError("OpenAI generation failed after all attempts.")

    def _call_sync_api(
        self,
        client: OpenAI,
        messages: list[dict[str, str]],
        temperature: float,
        max_tokens: int,
    ) -> Any:
        """Execute synchronous API call preferring Responses API with Chat Completions fallback."""
        if hasattr(client, "responses") and callable(getattr(client.responses, "create", None)):
            try:
                return client.responses.create(
                    model=self.model,  # type: ignore[arg-type]
                    input=messages,  # type: ignore[arg-type]
                    temperature=temperature,
                    max_output_tokens=max_tokens,
                )
            except AttributeError:
                # Fall back to chat.completions if responses endpoint attribute is missing
                logger.debug("Falling back from responses.create to chat.completions.create")
                pass

        return client.chat.completions.create(
            model=self.model,  # type: ignore[arg-type]
            messages=messages,  # type: ignore[arg-type]
            temperature=temperature,
            max_tokens=max_tokens,
        )

    async def _call_async_api(
        self,
        client: AsyncOpenAI,
        messages: list[dict[str, str]],
        temperature: float,
        max_tokens: int,
    ) -> Any:
        """Execute asynchronous API call preferring Responses API with Chat Completions fallback."""
        if hasattr(client, "responses") and callable(getattr(client.responses, "create", None)):
            try:
                return await client.responses.create(
                    model=self.model,  # type: ignore[arg-type]
                    input=messages,  # type: ignore[arg-type]
                    temperature=temperature,
                    max_output_tokens=max_tokens,
                )
            except AttributeError:
                logger.debug("Falling back from async responses.create to chat.completions.create")
                pass

        return await client.chat.completions.create(
            model=self.model,  # type: ignore[arg-type]
            messages=messages,  # type: ignore[arg-type]
            temperature=temperature,
            max_tokens=max_tokens,
        )

    @staticmethod
    def _extract_content(response: Any) -> str:
        """Safely extract generated content from an OpenAI response (Responses API or Chat Completions)."""
        if response is None:
            raise LLMResponseMalformedError("OpenAI returned null response.")

        # 1. Responses API response object
        if hasattr(response, "output_text"):
            text = getattr(response, "output_text", "")
            if text and str(text).strip():
                return str(text).strip()

        # 2. Responses API with output list inspection
        if hasattr(response, "output") and response.output:
            for item in response.output:
                if getattr(item, "type", None) == "message" and hasattr(item, "content"):
                    for content_part in getattr(item, "content", []):
                        part_text = getattr(content_part, "text", None)
                        if part_text and str(part_text).strip():
                            return str(part_text).strip()

        # 3. Chat Completions API response object
        if hasattr(response, "choices"):
            if not response.choices:
                raise LLMResponseMalformedError("OpenAI returned empty choices list.")
            first_choice = response.choices[0]
            if not hasattr(first_choice, "message") or not first_choice.message:
                raise LLMResponseMalformedError("OpenAI choice missing message object.")
            content = getattr(first_choice.message, "content", None)
            if content is None or not str(content).strip():
                raise LLMResponseMalformedError("OpenAI message content is null or empty.")
            return str(content).strip()

        raise LLMResponseMalformedError("OpenAI response format could not be parsed into text.")

    @staticmethod
    def _is_quota_or_billing_error(exc: openai.RateLimitError) -> bool:
        """Check if RateLimitError represents a non-retryable quota or billing exhaustion."""
        try:
            body = getattr(exc, "body", None)
            if isinstance(body, dict):
                err_dict = body.get("error", {})
                if isinstance(err_dict, dict):
                    code = str(err_dict.get("code") or "").lower()
                    err_type = str(err_dict.get("type") or "").lower()
                    msg = str(err_dict.get("message") or "").lower()
                    if "insufficient_quota" in code or "quota" in err_type or "billing" in msg:
                        return True
            err_str = str(exc).lower()
            if "insufficient_quota" in err_str or "exceeded your current quota" in err_str:
                return True
        except Exception:
            pass
        return False

    @staticmethod
    def _parse_retry_after(exc: Any) -> Optional[float]:
        """Attempt to extract numeric retry-after from error headers if available."""
        try:
            if hasattr(exc, "response") and exc.response is not None:
                headers = getattr(exc.response, "headers", {})
                ra = headers.get("retry-after")
                if ra:
                    return float(ra)
                # Some proxies or headers provide retry-after-ms
                ra_ms = headers.get("retry-after-ms")
                if ra_ms:
                    return float(ra_ms) / 1000.0
        except Exception:
            pass
        return None
