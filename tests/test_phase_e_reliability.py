"""
tests/test_phase_e_reliability.py
=================================
Phase E Reliability, Failure Isolation, and Dependency Fault Tolerance Tests.
"""
from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi.testclient import TestClient

from backend.app.config import AppSettings
from backend.app.dependencies import get_chat_service
from backend.app.llm.exceptions import LLMRateLimitError, LLMTimeoutError
from backend.app.main import create_app
from backend.app.services.chat_service import ChatService
from backend.retrieval.models import SearchResult


@pytest.fixture
def reliability_app():
    settings = AppSettings(
        app_env="testing",
        allowed_origins=["http://localhost:5173", "https://eurekasolutions.in"],
        rate_limit_per_minute=100,
    )
    app = create_app(settings=settings)
    return app


def _make_mock_chunk() -> SearchResult:
    return SearchResult(
        chunk_id="chunk-test-1",
        page_id="page-test-1",
        text="Eureka Solutions delivers comprehensive enterprise software, ERP, and cloud integration.",
        source_url="https://eurekasolutions.in/Eureka2026/services/enterprise-software",
        page_title="Enterprise Software Solutions",
        section_heading="Overview",
        score=0.85,
        metadata={
            "page_title": "Enterprise Software Solutions",
            "source_url": "https://eurekasolutions.in/Eureka2026/services/enterprise-software",
            "section_heading": "Overview",
        },
    )


def test_groq_upstream_timeout_returns_503(reliability_app):
    """
    When Groq LLM upstream call times out, ChatService catches LLMTimeoutError
    and returns TEMPORARILY_UNAVAILABLE with HTTP 503.
    """
    mock_retriever = MagicMock()
    mock_chunk = _make_mock_chunk()
    mock_retriever.retrieve.return_value = [mock_chunk]

    mock_groq = MagicMock()
    mock_groq.agenerate = AsyncMock(side_effect=LLMTimeoutError("Groq request timed out after 30s"))

    chat_service = ChatService(
        retriever=mock_retriever,
        llm_client=mock_groq,
        settings=reliability_app.state.settings,
    )
    reliability_app.dependency_overrides[get_chat_service] = lambda: chat_service

    with TestClient(reliability_app) as client:
        res = client.post(
            "/api/v1/chat",
            json={"message": "What is NetSuite?"},
            headers={"Origin": "http://localhost:5173"},
        )

        assert res.status_code == 503
        data = res.json()
        assert data["status"] == "temporarily_unavailable"
        assert "request_id" in data
        assert "temporarily unavailable" in data["answer"].lower()
        # No stack traces or private paths
        assert "Traceback" not in res.text
        assert "D:\\" not in res.text


def test_groq_upstream_rate_limit_returns_503(reliability_app):
    """
    When Groq LLM returns HTTP 429 rate limit, ChatService catches LLMRateLimitError
    and maps it to TEMPORARILY_UNAVAILABLE with HTTP 503.
    """
    mock_retriever = MagicMock()
    mock_chunk = _make_mock_chunk()
    mock_retriever.retrieve.return_value = [mock_chunk]

    mock_groq = MagicMock()
    mock_groq.agenerate = AsyncMock(
        side_effect=LLMRateLimitError("Upstream Groq rate limit hit (retry after 60s)")
    )

    chat_service = ChatService(
        retriever=mock_retriever,
        llm_client=mock_groq,
        settings=reliability_app.state.settings,
    )
    reliability_app.dependency_overrides[get_chat_service] = lambda: chat_service

    with TestClient(reliability_app) as client:
        res = client.post(
            "/api/v1/chat",
            json={"message": "What is NetSuite?"},
            headers={"Origin": "http://localhost:5173"},
        )

        assert res.status_code == 503
        data = res.json()
        assert data["status"] == "temporarily_unavailable"
        assert "request_id" in data
        assert "Traceback" not in res.text


def test_retriever_failure_returns_503(reliability_app):
    """
    When vector retriever fails (e.g. ChromaDB connection lost), ChatService catches
    the error and returns TEMPORARILY_UNAVAILABLE with HTTP 503.
    """
    mock_retriever = MagicMock()
    mock_retriever.retrieve.side_effect = RuntimeError("ChromaDB socket closed unexpectedly")

    mock_groq = MagicMock()

    chat_service = ChatService(
        retriever=mock_retriever,
        llm_client=mock_groq,
        settings=reliability_app.state.settings,
    )
    reliability_app.dependency_overrides[get_chat_service] = lambda: chat_service

    with TestClient(reliability_app) as client:
        res = client.post(
            "/api/v1/chat",
            json={"message": "Tell me about ERP"},
            headers={"Origin": "http://localhost:5173"},
        )

        assert res.status_code == 503
        data = res.json()
        assert data["status"] == "temporarily_unavailable"
        assert "request_id" in data
        assert "Traceback" not in res.text


def test_health_ready_probe_reflects_dependency_failure(reliability_app):
    """
    When vector store is uninitialized or missing collection, /health/ready returns 503.
    """
    with TestClient(reliability_app) as client:
        # Liveness must always return 200
        res_live = client.get("/health/live")
        assert res_live.status_code == 200
        assert res_live.json() == {"status": "ok"}

        # Simulate missing collection or uninitialized store
        reliability_app.state.retriever = None
        reliability_app.state.vector_store = None

        res_ready = client.get("/health/ready")
        assert res_ready.status_code == 503
        data = res_ready.json()
        assert data["status"] == "not_ready"
