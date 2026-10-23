"""
backend/tests/test_groq_client.py
=================================
Unit tests for GroqClient adapter, timeouts, retries, and sanitized exception handling.
Exercises provider error mapping with complete isolation (zero real external calls).
"""
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
import groq

from backend.app.llm.exceptions import (
    LLMBadRequestError,
    LLMConfigError,
    LLMRateLimitError,
    LLMResponseMalformedError,
    LLMTimeoutError,
    LLMUnavailableError,
)
from backend.app.llm.groq_client import GroqClient


def test_groq_client_unconfigured():
    client = GroqClient(api_key=None, model=None)
    assert not client.is_configured
    with pytest.raises(LLMConfigError):
        client.generate([{"role": "user", "content": "hi"}])


def test_groq_client_success():
    client = GroqClient(api_key="gsk-dummy-test-key", model="llama-3.3-70b-versatile")
    assert client.is_configured

    mock_choice = MagicMock()
    mock_choice.message.content = "Eureka Solutions offers ERP and cloud solutions."
    mock_response = MagicMock()
    mock_response.choices = [mock_choice]

    with patch.object(client, "_get_sync_client") as mock_get_client:
        mock_sync = MagicMock()
        mock_sync.chat.completions.create.return_value = mock_response
        mock_get_client.return_value = mock_sync

        answer = client.generate([{"role": "user", "content": "services"}])
        assert answer == "Eureka Solutions offers ERP and cloud solutions."
        assert mock_sync.chat.completions.create.call_count == 1


@pytest.mark.anyio
async def test_groq_client_async_success():
    client = GroqClient(api_key="gsk-dummy-test-key", model="llama-3.3-70b-versatile")
    mock_choice = MagicMock()
    mock_choice.message.content = "Async answer."
    mock_response = MagicMock()
    mock_response.choices = [mock_choice]

    with patch.object(client, "_get_async_client") as mock_get_client:
        mock_async = MagicMock()
        mock_async.chat.completions.create = AsyncMock(return_value=mock_response)
        mock_get_client.return_value = mock_async

        answer = await client.agenerate([{"role": "user", "content": "hello"}])
        assert answer == "Async answer."


def test_groq_client_timeout_and_retries():
    client = GroqClient(
        api_key="gsk-dummy",
        model="llama-3.3-70b-versatile",
        timeout_seconds=1.0,
        max_retries=2,
    )

    with patch.object(client, "_get_sync_client") as mock_get_client:
        mock_sync = MagicMock()
        # Simulate timeouts across all attempts
        mock_sync.chat.completions.create.side_effect = groq.APITimeoutError(request=MagicMock())
        mock_get_client.return_value = mock_sync

        with patch("time.sleep"):  # Avoid sleep delays during test
            with pytest.raises(LLMTimeoutError):
                client.generate([{"role": "user", "content": "test"}])

        # Initial attempt + 2 retries = 3 attempts total
        assert mock_sync.chat.completions.create.call_count == 3


def test_groq_client_rate_limit_429():
    client = GroqClient(api_key="gsk-dummy", model="llama-3.3-70b-versatile", max_retries=1)

    mock_http_response = MagicMock()
    mock_http_response.headers = {"retry-after": "15"}
    mock_http_response.status_code = 429

    err = groq.RateLimitError(
        message="Rate limit exceeded",
        response=mock_http_response,
        body={},
    )

    with patch.object(client, "_get_sync_client") as mock_get_client:
        mock_sync = MagicMock()
        mock_sync.chat.completions.create.side_effect = err
        mock_get_client.return_value = mock_sync

        with pytest.raises(LLMRateLimitError) as exc_info:
            client.generate([{"role": "user", "content": "test"}])

        assert exc_info.value.retry_after == 15.0


def test_groq_client_auth_error_no_retry():
    client = GroqClient(api_key="bad-key", model="llama-3.3-70b-versatile", max_retries=2)

    err = groq.AuthenticationError(
        message="Invalid API Key",
        response=MagicMock(status_code=401),
        body={},
    )

    with patch.object(client, "_get_sync_client") as mock_get_client:
        mock_sync = MagicMock()
        mock_sync.chat.completions.create.side_effect = err
        mock_get_client.return_value = mock_sync

        with pytest.raises(LLMConfigError) as exc_info:
            client.generate([{"role": "user", "content": "test"}])

        # Never retry on permanent authentication error
        assert mock_sync.chat.completions.create.call_count == 1
        assert "bad-key" not in str(exc_info.value)


def test_groq_client_malformed_response():
    client = GroqClient(api_key="gsk-dummy", model="llama-3.3-70b-versatile")
    mock_response = MagicMock()
    mock_response.choices = []

    with patch.object(client, "_get_sync_client") as mock_get_client:
        mock_sync = MagicMock()
        mock_sync.chat.completions.create.return_value = mock_response
        mock_get_client.return_value = mock_sync

        with pytest.raises(LLMResponseMalformedError):
            client.generate([{"role": "user", "content": "hi"}])
