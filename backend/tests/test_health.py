"""
backend/tests/test_health.py
============================
Tests for /health/live and /health/ready endpoints.
Verifies readiness dependency checking without making LLM calls.
"""
from unittest.mock import MagicMock

from fastapi.testclient import TestClient

from backend.app.dependencies import get_vector_store
from backend.app.main import create_app


def test_health_live_endpoint():
    app = create_app()
    with TestClient(app) as client:
        res = client.get("/health/live")
        assert res.status_code == 200
        assert res.json() == {"status": "ok"}
        assert "x-request-id" in res.headers


def test_health_ready_success():
    app = create_app()
    mock_store = MagicMock()
    mock_store.count.return_value = 3796

    app.dependency_overrides[get_vector_store] = lambda: mock_store

    with TestClient(app) as client:
        res = client.get("/health/ready")
        assert res.status_code == 200
        body = res.json()
        assert body["status"] == "ready"
        assert body["chunks_count"] == 3796
        assert body["vector_store"] == "ok"


def test_health_ready_uninitialized_store():
    app = create_app()
    app.dependency_overrides[get_vector_store] = lambda: None

    with TestClient(app) as client:
        res = client.get("/health/ready")
        assert res.status_code == 503
        body = res.json()
        assert body["status"] == "not_ready"
        assert body["reason"] == "vector_store_uninitialized"


def test_health_ready_empty_collection():
    app = create_app()
    mock_store = MagicMock()
    mock_store.count.return_value = 0

    app.dependency_overrides[get_vector_store] = lambda: mock_store

    with TestClient(app) as client:
        res = client.get("/health/ready")
        assert res.status_code == 503
        body = res.json()
        assert body["status"] == "not_ready"
        assert body["reason"] == "collection_empty_or_missing"


def test_health_ready_store_exception():
    app = create_app()
    mock_store = MagicMock()
    mock_store.count.side_effect = RuntimeError("Disk IO Error")

    app.dependency_overrides[get_vector_store] = lambda: mock_store

    with TestClient(app) as client:
        res = client.get("/health/ready")
        assert res.status_code == 503
        body = res.json()
        assert body["status"] == "not_ready"
        assert body["reason"] == "vector_store_error"
