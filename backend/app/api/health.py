"""
backend/app/api/health.py
=========================
Health check endpoints:
- GET /health/live: lightweight process liveness.
- GET /health/ready: verification of vector store and collection dependencies.
Follows Problem Statement §9.2 and Architecture §6.2.
"""
from __future__ import annotations

import logging
from typing import Any

from fastapi import APIRouter, Depends, Request, Response, status

from backend.app.config import AppSettings
from backend.app.dependencies import get_app_settings, get_vector_store

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/health", tags=["Health"])


@router.get(
    "/live",
    status_code=status.HTTP_200_OK,
    summary="Process Liveness Check",
    description="Indicates that the HTTP process is running. Fast, performs no slow external calls.",
)
async def health_live() -> dict[str, str]:
    """Lightweight liveness check."""
    return {"status": "ok"}


@router.get(
    "/ready",
    summary="Application Readiness Check",
    description="Verifies vector store availability and collection readiness before traffic is routed.",
)
async def health_ready(
    request: Request,
    response: Response,
    settings: AppSettings = Depends(get_app_settings),
    vector_store: Any = Depends(get_vector_store),
) -> dict[str, Any]:
    """
    Readiness verification:
    - Checks that vector store is initialized.
    - Checks that configured collection exists and is populated.
    - Never calls Groq API or performs vector search.
    - Returns 503 Service Unavailable if unready.
    """
    if vector_store is None:
        logger.warning("Readiness probe failed: vector store is not initialized.")
        response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE
        return {
            "status": "not_ready",
            "reason": "vector_store_uninitialized",
            "detail": "Vector store client is not active.",
        }

    if getattr(request.app.state, "index_incompatible", False):
        reason = getattr(
            request.app.state,
            "incompatibility_reason",
            "Vector index is incompatible with configured embedding model.",
        )
        logger.warning("Readiness probe failed: %s", reason)
        response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE
        return {
            "status": "not_ready",
            "reason": "index_incompatible",
            "detail": reason,
        }

    try:
        # Check collection existence and record count
        count = vector_store.count()
        if count <= 0:
            logger.warning(
                "Readiness probe failed: collection '%s' is empty or missing.",
                settings.vector_collection_name,
            )
            response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE
            return {
                "status": "not_ready",
                "reason": "collection_empty_or_missing",
                "collection": settings.vector_collection_name,
                "detail": "Vector index collection is empty or not found.",
            }

        response.status_code = status.HTTP_200_OK
        return {
            "status": "ready",
            "vector_store": "ok",
            "collection": settings.vector_collection_name,
            "chunks_count": count,
        }

    except Exception as exc:
        logger.error("Readiness check exception: %s", type(exc).__name__)
        response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE
        return {
            "status": "not_ready",
            "reason": "vector_store_error",
            "detail": "Error communicating with vector storage.",
        }
