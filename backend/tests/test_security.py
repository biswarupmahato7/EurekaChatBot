"""
backend/tests/test_security.py
==============================
Security, privacy, and prompt-injection guardrail tests for Eureka RAG Chatbot.
Verifies proxy handling, credential isolation, and strict input boundaries.
"""
from unittest.mock import MagicMock

from fastapi.testclient import TestClient

from backend.app.config import AppSettings
from backend.app.dependencies import get_chat_service
from backend.app.main import create_app
from backend.app.middleware.rate_limit import RateLimitMiddleware


def test_no_secrets_in_error_responses():
    app = create_app(
        settings=AppSettings(
            openai_api_key="sk-proj-super-secret-key-12345",
            groq_api_key="gsk-super-secret-key-12345",
        )
    )

    # Force a 500 error to test exception handler safety
    mock_service = MagicMock()
    mock_service.handle_chat_request.side_effect = RuntimeError(
        "Internal crash referencing secrets sk-proj-super-secret-key-12345, gsk-super-secret-key-12345 and path /var/secrets"
    )
    app.dependency_overrides[get_chat_service] = lambda: mock_service

    with TestClient(app, raise_server_exceptions=False) as client:
        res = client.post("/api/v1/chat", json={"message": "Crash test"})
        assert res.status_code == 500
        text = res.text
        # Assert secrets, filesystem paths, and internal stack traces are redacted
        assert "sk-proj-super-secret-key-12345" not in text
        assert "gsk-super-secret-key-12345" not in text
        assert "/var/secrets" not in text
        assert "RuntimeError" not in text
        body = res.json()
        assert body["error"]["code"] == "internal_error"
        assert body["error"]["message"] == "An unexpected internal server error occurred."
        assert "request_id" in body["error"]


def test_untrusted_proxy_x_forwarded_for_ignored():
    # Configure with NO trusted proxies
    settings = AppSettings(trusted_proxies=[])
    app = create_app(settings=settings)

    middleware = RateLimitMiddleware(
        app=MagicMock(),
        trusted_proxies=[],
    )

    mock_request = MagicMock()
    mock_request.client.host = "192.168.1.50"
    mock_request.headers = {"x-forwarded-for": "203.0.113.195, 10.0.0.1"}

    # Must ignore X-Forwarded-For and use direct client host because proxy is untrusted
    resolved_ip = middleware._resolve_client_ip(mock_request)
    assert resolved_ip == "192.168.1.50"


def test_trusted_proxy_x_forwarded_for_accepted():
    # Configure reverse proxies in chain as trusted
    middleware = RateLimitMiddleware(
        app=MagicMock(),
        trusted_proxies=["192.168.1.50", "10.0.0.1"],
    )

    mock_request = MagicMock()
    mock_request.client.host = "192.168.1.50"
    mock_request.headers = {"x-forwarded-for": "203.0.113.195, 10.0.0.1"}

    # Safely extracts the real client IP (rightmost untrusted client IP)
    resolved_ip = middleware._resolve_client_ip(mock_request)
    assert resolved_ip == "203.0.113.195"


def test_no_secrets_in_health_probes():
    app = create_app(
        settings=AppSettings(
            openai_api_key="sk-proj-super-secret-key-12345",
            groq_api_key="gsk-super-secret-key-12345",
        )
    )
    with TestClient(app) as client:
        res_live = client.get("/health/live")
        assert "sk-" not in res_live.text
        assert "gsk-" not in res_live.text

        res_ready = client.get("/health/ready")
        assert "sk-" not in res_ready.text
        assert "gsk-" not in res_ready.text
