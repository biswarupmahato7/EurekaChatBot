"""
backend/tests/test_openai_client.py
===================================
Unit tests for OpenAIClient adapter, timeouts, bounded retries, and sanitized exception handling.
Exercises provider error mapping with complete isolation (zero real external calls).
"""
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
import openai

from backend.app.llm.exceptions import (
    LLMBadRequestError,
    LLMConfigError,
    LLMError,
    LLMRateLimitError,
    LLMResponseMalformedError,
    LLMTimeoutError,
    LLMUnavailableError,
)
from backend.app.llm.openai_client import OpenAIClient


def test_openai_client_unconfigured():
    client = OpenAIClient(api_key=None, model=None)
    assert not client.is_configured
    with pytest.raises(LLMConfigError):
        client.generate([{"role": "user", "content": "hi"}])


def test_openai_client_repr_no_leak():
    client = OpenAIClient(api_key="sk-secret-key-12345", model="gpt-4o-mini")
    rep = repr(client)
    assert "sk-secret-key-12345" not in rep
    assert "gpt-4o-mini" in rep
    assert "set" in rep


def test_openai_client_responses_api_success():
    client = OpenAIClient(api_key="sk-dummy-test-key", model="gpt-4o-mini")
    assert client.is_configured

    mock_response = MagicMock()
    mock_response.output_text = "Eureka Solutions provides bespoke software solutions."

    with patch.object(client, "_get_sync_client") as mock_get_client:
        mock_sync = MagicMock()
        mock_sync.responses.create.return_value = mock_response
        mock_get_client.return_value = mock_sync

        answer = client.generate([{"role": "user", "content": "services"}])
        assert answer == "Eureka Solutions provides bespoke software solutions."
        assert mock_sync.responses.create.call_count == 1


@pytest.mark.anyio
async def test_openai_client_async_responses_api_success():
    client = OpenAIClient(api_key="sk-dummy-test-key", model="gpt-4o-mini")
    mock_response = MagicMock()
    mock_response.output_text = "Async response from OpenAI Responses API."

    with patch.object(client, "_get_async_client") as mock_get_client:
        mock_async = MagicMock()
        mock_async.responses.create = AsyncMock(return_value=mock_response)
        mock_get_client.return_value = mock_async

        answer = await client.agenerate([{"role": "user", "content": "hello"}])
        assert answer == "Async response from OpenAI Responses API."
        assert mock_async.responses.create.call_count == 1


def test_openai_client_chat_completions_fallback():
    client = OpenAIClient(api_key="sk-dummy-test-key", model="gpt-4o-mini")

    mock_choice = MagicMock()
    mock_choice.message.content = "Fallback chat completion response."
    mock_chat_response = MagicMock(spec=["choices"])
    mock_chat_response.choices = [mock_choice]

    with patch.object(client, "_get_sync_client") as mock_get_client:
        mock_sync = MagicMock()
        mock_sync.responses.create.side_effect = AttributeError("responses not supported")
        mock_sync.chat.completions.create.return_value = mock_chat_response
        mock_get_client.return_value = mock_sync

        answer = client.generate([{"role": "user", "content": "hello"}])
        assert answer == "Fallback chat completion response."
        assert mock_sync.chat.completions.create.call_count == 1


def test_openai_client_timeout_and_retries():
    client = OpenAIClient(
        api_key="sk-dummy",
        model="gpt-4o-mini",
        timeout_seconds=1.0,
        max_retries=2,
    )

    with patch.object(client, "_get_sync_client") as mock_get_client:
        mock_sync = MagicMock()
        mock_sync.responses.create.side_effect = openai.APITimeoutError(request=MagicMock())
        mock_get_client.return_value = mock_sync

        with patch("time.sleep"):  # Avoid sleep delays during test
            with pytest.raises(LLMTimeoutError) as exc_info:
                client.generate([{"role": "user", "content": "test"}])

        assert "timed out" in str(exc_info.value).lower()
        # Initial attempt + 2 retries = 3 attempts total
        assert mock_sync.responses.create.call_count == 3


def test_openai_client_rate_limit_429():
    client = OpenAIClient(api_key="sk-dummy", model="gpt-4o-mini", max_retries=1)

    mock_http_response = MagicMock()
    mock_http_response.headers = {"retry-after": "15"}
    mock_http_response.status_code = 429

    err = openai.RateLimitError(
        message="Rate limit reached for requests",
        response=mock_http_response,
        body={"error": {"code": "rate_limit_exceeded"}},
    )

    with patch.object(client, "_get_sync_client") as mock_get_client:
        mock_sync = MagicMock()
        mock_sync.responses.create.side_effect = err
        mock_get_client.return_value = mock_sync

        with pytest.raises(LLMRateLimitError) as exc_info:
            client.generate([{"role": "user", "content": "test"}])

        assert exc_info.value.retry_after == 15.0


def test_openai_client_quota_exhausted_no_retry():
    client = OpenAIClient(api_key="sk-dummy", model="gpt-4o-mini", max_retries=2)

    mock_http_response = MagicMock()
    mock_http_response.status_code = 429
    err = openai.RateLimitError(
        message="You exceeded your current quota, please check your plan and billing details.",
        response=mock_http_response,
        body={"error": {"code": "insufficient_quota", "type": "insufficient_quota"}},
    )

    with patch.object(client, "_get_sync_client") as mock_get_client:
        mock_sync = MagicMock()
        mock_sync.responses.create.side_effect = err
        mock_get_client.return_value = mock_sync

        with pytest.raises(LLMUnavailableError) as exc_info:
            client.generate([{"role": "user", "content": "test"}])

        # Permanent quota error: must NEVER retry
        assert mock_sync.responses.create.call_count == 1
        assert "quota" in str(exc_info.value).lower()


def test_openai_client_auth_error_no_retry():
    client = OpenAIClient(api_key="bad-sk-key-9999", model="gpt-4o-mini", max_retries=2)

    err = openai.AuthenticationError(
        message="Incorrect API key provided: bad-sk-key-9999",
        response=MagicMock(status_code=401),
        body={},
    )

    with patch.object(client, "_get_sync_client") as mock_get_client:
        mock_sync = MagicMock()
        mock_sync.responses.create.side_effect = err
        mock_get_client.return_value = mock_sync

        with pytest.raises(LLMConfigError) as exc_info:
            client.generate([{"role": "user", "content": "test"}])

        # Never retry on permanent authentication error
        assert mock_sync.responses.create.call_count == 1
        assert "bad-sk-key-9999" not in str(exc_info.value)


def test_openai_client_model_not_found():
    client = OpenAIClient(api_key="sk-dummy", model="non-existent-model", max_retries=2)

    err = openai.NotFoundError(
        message="The model non-existent-model does not exist",
        response=MagicMock(status_code=404),
        body={},
    )

    with patch.object(client, "_get_sync_client") as mock_get_client:
        mock_sync = MagicMock()
        mock_sync.responses.create.side_effect = err
        mock_get_client.return_value = mock_sync

        with pytest.raises(LLMBadRequestError) as exc_info:
            client.generate([{"role": "user", "content": "test"}])

        # Never retry on invalid/not found model
        assert mock_sync.responses.create.call_count == 1


def test_openai_client_transient_server_error_retries():
    client = OpenAIClient(api_key="sk-dummy", model="gpt-4o-mini", max_retries=2)

    err = openai.InternalServerError(
        message="The server had an error while processing your request.",
        response=MagicMock(status_code=500),
        body={},
    )

    with patch.object(client, "_get_sync_client") as mock_get_client:
        mock_sync = MagicMock()
        mock_sync.responses.create.side_effect = err
        mock_get_client.return_value = mock_sync

        with patch("time.sleep"):
            with pytest.raises(LLMUnavailableError):
                client.generate([{"role": "user", "content": "test"}])

        # Retried up to max_retries
        assert mock_sync.responses.create.call_count == 3


def test_openai_client_malformed_response_empty():
    client = OpenAIClient(api_key="sk-dummy", model="gpt-4o-mini")

    mock_response = MagicMock(spec=["output_text"])
    mock_response.output_text = ""

    with patch.object(client, "_get_sync_client") as mock_get_client:
        mock_sync = MagicMock()
        mock_sync.responses.create.return_value = mock_response
        mock_get_client.return_value = mock_sync

        with pytest.raises(LLMResponseMalformedError):
            client.generate([{"role": "user", "content": "hi"}])
