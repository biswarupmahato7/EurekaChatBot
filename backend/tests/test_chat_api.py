"""
backend/tests/test_chat_api.py
==============================
Integration tests for POST /api/v1/chat endpoint, request validation,
CORS policies, rate limiting, and response serialization.
"""
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi.testclient import TestClient

from backend.app.config import AppSettings
from backend.app.dependencies import get_chat_service
from backend.app.main import create_app
from backend.app.schemas.chat import ChatResponse, ChatStatus, SourceItem
from backend.app.services.chat_service import ChatService


@pytest.fixture
def mock_chat_service():
    service = MagicMock(spec=ChatService)
    # Default successful mock response
    default_response = ChatResponse(
        request_id="req-test-123",
        answer="Eureka Solutions provides comprehensive enterprise software integrations.",
        status=ChatStatus.ANSWERED,
        sources=[
            SourceItem(
                title="Services",
                url="https://eurekasolutions.in/Eureka2026/services/",
                snippet="Comprehensive enterprise software integrations.",
            )
        ],
    )
    service.handle_chat_request = AsyncMock(
        return_value=(
            default_response,
            {
                "total_latency_seconds": 0.05,
                "retrieval_latency_seconds": 0.02,
                "generation_latency_seconds": 0.03,
                "retrieved_chunks_count": 1,
                "validated_sources_count": 1,
                "status": "answered",
                "error_category": None,
            },
        )
    )
    return service


def test_chat_success(mock_chat_service):
    app = create_app()
    app.dependency_overrides[get_chat_service] = lambda: mock_chat_service

    with TestClient(app) as client:
        res = client.post(
            "/api/v1/chat",
            json={"message": "What services does Eureka Solutions provide?"},
        )
        assert res.status_code == 200
        data = res.json()
        assert data["status"] == "answered"
        assert "Eureka Solutions provides" in data["answer"]
        assert len(data["sources"]) == 1
        assert data["sources"][0]["url"] == "https://eurekasolutions.in/Eureka2026/services/"
        assert "x-request-id" in res.headers


def test_chat_validation_empty_and_whitespace(mock_chat_service):
    app = create_app()
    app.dependency_overrides[get_chat_service] = lambda: mock_chat_service

    with TestClient(app) as client:
        # Empty string
        res_empty = client.post("/api/v1/chat", json={"message": ""})
        assert res_empty.status_code == 422
        body_empty = res_empty.json()
        assert "error" in body_empty
        assert body_empty["error"]["code"] == "validation_error"

        # Whitespace-only string
        res_ws = client.post("/api/v1/chat", json={"message": "    \n   "})
        assert res_ws.status_code == 422


def test_chat_validation_length_bounds(mock_chat_service):
    app = create_app()
    app.dependency_overrides[get_chat_service] = lambda: mock_chat_service

    with TestClient(app) as client:
        # Exactly 2,000 characters should be accepted
        exact_2000 = "a" * 2000
        res_exact = client.post("/api/v1/chat", json={"message": exact_2000})
        assert res_exact.status_code == 200

        # 2,001 characters should be rejected
        too_long = "a" * 2001
        res_too_long = client.post("/api/v1/chat", json={"message": too_long})
        assert res_too_long.status_code == 422
        assert res_too_long.json()["error"]["code"] == "validation_error"


def test_chat_validation_malformed_json(mock_chat_service):
    app = create_app()
    app.dependency_overrides[get_chat_service] = lambda: mock_chat_service

    with TestClient(app) as client:
        res = client.post(
            "/api/v1/chat",
            content="not valid json string",
            headers={"Content-Type": "application/json"},
        )
        assert res.status_code == 422
        assert "x-request-id" in res.headers


def test_chat_out_of_scope_status(mock_chat_service):
    out_of_scope_res = ChatResponse(
        request_id="req-out",
        answer="I am the Ask Eureka AI assistant... out of scope.",
        status=ChatStatus.OUT_OF_SCOPE,
        sources=[],
    )
    mock_chat_service.handle_chat_request = AsyncMock(
        return_value=(out_of_scope_res, {"status": "out_of_scope"})
    )

    app = create_app()
    app.dependency_overrides[get_chat_service] = lambda: mock_chat_service

    with TestClient(app) as client:
        res = client.post(
            "/api/v1/chat",
            json={"message": "What is the weather in Tokyo?"},
        )
        assert res.status_code == 200
        data = res.json()
        assert data["status"] == "out_of_scope"
        assert data["sources"] == []


def test_chat_temporarily_unavailable_status(mock_chat_service):
    unavail_res = ChatResponse(
        request_id="req-503",
        answer="Our service is temporarily unavailable.",
        status=ChatStatus.TEMPORARILY_UNAVAILABLE,
        sources=[],
    )
    mock_chat_service.handle_chat_request = AsyncMock(
        return_value=(unavail_res, {"status": "temporarily_unavailable", "error_category": "timeout"})
    )

    app = create_app()
    app.dependency_overrides[get_chat_service] = lambda: mock_chat_service

    with TestClient(app) as client:
        res = client.post(
            "/api/v1/chat",
            json={"message": "Services?"},
        )
        # Logical status TEMPORARILY_UNAVAILABLE maps to HTTP 503
        assert res.status_code == 503
        data = res.json()
        assert data["status"] == "temporarily_unavailable"


def test_cors_allowed_and_blocked_origins(mock_chat_service):
    settings = AppSettings(
        allowed_origins=["http://localhost:3000", "https://eurekasolutions.in"]
    )
    app = create_app(settings=settings)
    app.dependency_overrides[get_chat_service] = lambda: mock_chat_service

    with TestClient(app) as client:
        # 1. Allowed origin
        res_allowed = client.options(
            "/api/v1/chat",
            headers={
                "Origin": "http://localhost:3000",
                "Access-Control-Request-Method": "POST",
            },
        )
        assert res_allowed.headers.get("access-control-allow-origin") == "http://localhost:3000"

        # 2. Disallowed origin
        res_blocked = client.options(
            "/api/v1/chat",
            headers={
                "Origin": "https://malicious-site.com",
                "Access-Control-Request-Method": "POST",
            },
        )
        assert "access-control-allow-origin" not in res_blocked.headers


def test_rate_limiting(mock_chat_service):
    # Set limit to 3 requests per minute for this test
    settings = AppSettings(rate_limit_per_minute=3)
    app = create_app(settings=settings)
    app.dependency_overrides[get_chat_service] = lambda: mock_chat_service

    with TestClient(app) as client:
        # First 3 requests succeed
        for _ in range(3):
            r = client.post("/api/v1/chat", json={"message": "hello"})
            assert r.status_code == 200

        # 4th request exceeds rate limit
        r_blocked = client.post("/api/v1/chat", json={"message": "hello"})
        assert r_blocked.status_code == 429
        body = r_blocked.json()
        assert body["error"]["code"] == "rate_limit_exceeded"
        assert "x-request-id" in r_blocked.headers
