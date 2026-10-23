"""
backend/app/dependencies.py
===========================
FastAPI dependency injection providers for settings, retriever, LLM client, and chat service.
"""
from __future__ import annotations

from functools import lru_cache
from typing import Any, Optional

from fastapi import Depends, Request

from backend.app.config import AppSettings
from backend.app.llm.groq_client import GroqClient
from backend.app.llm.openai_client import OpenAIClient
from backend.app.services.chat_service import ChatService


@lru_cache()
def get_app_settings() -> AppSettings:
    """Return cached application settings loaded from environment."""
    return AppSettings()


def get_llm_client(
    request: Request,
    settings: AppSettings = Depends(get_app_settings),
) -> Any:
    """Obtain the configured LLM client from application state or create one."""
    client = getattr(request.app.state, "llm_client", None)
    if client is None:
        provider = settings.llm_provider.strip().lower()
        if provider == "groq":
            client = GroqClient(
                api_key=settings.groq_api_key,
                model=settings.groq_model,
                timeout_seconds=settings.groq_timeout_seconds,
                max_retries=settings.groq_max_retries,
                max_output_tokens=settings.groq_max_output_tokens,
            )
        else:
            client = OpenAIClient(
                api_key=settings.openai_api_key,
                model=settings.openai_model,
                timeout_seconds=settings.openai_timeout_seconds,
                max_retries=settings.openai_max_retries,
                max_output_tokens=settings.openai_max_output_tokens,
            )
        request.app.state.llm_client = client
        request.app.state.openai_client = client
        request.app.state.groq_client = client
    return client


def get_openai_client(
    request: Request,
    settings: AppSettings = Depends(get_app_settings),
) -> OpenAIClient:
    """Obtain the configured OpenAIClient."""
    return get_llm_client(request, settings)


def get_groq_client(
    request: Request,
    settings: AppSettings = Depends(get_app_settings),
) -> Any:
    """Legacy dependency helper for GroqClient or active LLM client."""
    return get_llm_client(request, settings)


def get_retriever(request: Request) -> Optional[object]:
    """Obtain the initialized Phase B SemanticRetriever from application state."""
    return getattr(request.app.state, "retriever", None)


def get_vector_store(request: Request) -> Optional[object]:
    """Obtain the initialized Phase B BaseVectorStore from application state."""
    return getattr(request.app.state, "vector_store", None)


def get_chat_service(
    request: Request,
    settings: AppSettings = Depends(get_app_settings),
    llm_client: Any = Depends(get_llm_client),
) -> ChatService:
    """
    Construct the ChatService with dependencies.
    Allows easy overrides in pytest via app.dependency_overrides.
    """
    retriever = get_retriever(request)
    return ChatService(
        retriever=retriever,
        llm_client=llm_client,
        settings=settings,
    )
