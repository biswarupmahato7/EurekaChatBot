"""
backend/app/api/chat.py
=======================
Primary Chat QA API endpoint: POST /api/v1/chat.
Follows Problem Statement §9.2, §11 and Architecture §6.2.
"""
from __future__ import annotations

import logging
from typing import Any

from fastapi import APIRouter, Depends, Request, Response, status

from backend.app.config import AppSettings
from backend.app.dependencies import get_app_settings, get_chat_service
from backend.app.schemas.chat import ChatRequest, ChatResponse, ChatStatus
from backend.app.services.chat_service import ChatService

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1", tags=["Chat"])


@router.post(
    "/chat",
    response_model=ChatResponse,
    summary="Ask Eureka Solutions Chatbot",
    description=(
        "Submit a user inquiry to receive a grounded answer with citations extracted from the "
        "Eureka Solutions website corpus."
    ),
    responses={
        200: {
            "description": "Grounded response, conversational fallback, or scope notification.",
            "model": ChatResponse,
        },
        400: {"description": "Malformed JSON or validation error."},
        429: {"description": "Rate limit exceeded."},
        503: {
            "description": "Temporary service unavailability (retrieval or LLM dependency).",
            "model": ChatResponse,
        },
    },
)
async def chat_endpoint(
    chat_request: ChatRequest,
    request: Request,
    response: Response,
    chat_service: ChatService = Depends(get_chat_service),
    settings: AppSettings = Depends(get_app_settings),
) -> ChatResponse:
    """
    Execute full RAG pipeline for the visitor's question.
    """
    # 1. Retrieve correlation request_id attached by RequestIdMiddleware
    request_id = getattr(request.state, "request_id", None) or "req-unknown"

    # 2. Process query through ChatService
    chat_response, metrics = await chat_service.handle_chat_request(
        request=chat_request,
        request_id=request_id,
    )

    # 3. Map application outcome status to appropriate HTTP status code
    if chat_response.status == ChatStatus.TEMPORARILY_UNAVAILABLE:
        response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE
    else:
        response.status_code = status.HTTP_200_OK

    # 4. Privacy-conscious structured operational logging
    logger.info(
        "Chat request processed [req_id=%s, endpoint=/api/v1/chat, outcome=%s, http_status=%d, "
        "duration=%.3fs, retrieval_dur=%.3fs, gen_dur=%.3fs, chunks=%d, citations=%d, err=%s]",
        request_id,
        chat_response.status.value,
        response.status_code,
        metrics.get("total_latency_seconds", 0.0),
        metrics.get("retrieval_latency_seconds", 0.0),
        metrics.get("generation_latency_seconds", 0.0),
        metrics.get("retrieved_chunks_count", 0),
        metrics.get("validated_sources_count", 0),
        metrics.get("error_category") or "none",
    )

    return chat_response
