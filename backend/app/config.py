"""
backend/app/config.py
=====================
Validated settings for the Eureka RAG Chatbot FastAPI service.
Extends BackendSettings with web API, CORS, rate limiting, and Groq configuration.
"""
from __future__ import annotations

import logging
from pathlib import Path
from typing import Any, Optional
from urllib.parse import urlparse

from pydantic import Field, field_validator, model_validator

from backend.config import BackendSettings

logger = logging.getLogger(__name__)


class AppSettings(BackendSettings):
    """Configuration for the FastAPI backend and RAG chat services."""

    # ── Web Application ──────────────────────────────────────────────────────
    app_host: str = "0.0.0.0"
    app_port: int = 8000
    api_base_path: str = "/api/v1"

    @model_validator(mode="before")
    @classmethod
    def resolve_port_from_env(cls, data: Any) -> Any:
        import os
        if isinstance(data, dict):
            if "app_port" not in data and "PORT" in os.environ:
                try:
                    data["app_port"] = int(os.environ["PORT"])
                except ValueError:
                    pass
        elif data is None and "PORT" in os.environ:
            data = {"app_port": int(os.environ["PORT"])}
        return data

    allowed_origins: list[str] | str = Field(
        default_factory=lambda: [
            "http://localhost:3000",
            "http://127.0.0.1:3000",
            "https://eurekasolutions.in",
        ]
    )
    enable_docs: Optional[bool] = None

    # ── Limits & Security ────────────────────────────────────────────────────
    max_message_characters: int = Field(default=2000, ge=1, le=2000)
    rate_limit_per_minute: int = Field(default=60, ge=1, le=1000)
    trusted_proxies: list[str] | str = Field(default_factory=list)
    log_query_text: bool = False  # Disabled by default for privacy

    # ── LLM Provider Configuration ──────────────────────────────────────────
    llm_provider: str = Field(default="openai")

    # ── OpenAI LLM Configuration ────────────────────────────────────────────
    openai_api_key: Optional[str] = None
    openai_model: str = "gpt-4o-mini"
    openai_timeout_seconds: float = Field(default=30.0, gt=0, le=120)
    openai_max_retries: int = Field(default=2, ge=0, le=5)
    openai_max_output_tokens: int = Field(default=1024, ge=16, le=4096)

    # ── Groq LLM Configuration (Legacy / Explicit Selection) ─────────────────
    groq_api_key: Optional[str] = None
    groq_model: str = "llama-3.3-70b-versatile"
    groq_timeout_seconds: float = Field(default=30.0, gt=0, le=120)
    groq_max_retries: int = Field(default=2, ge=0, le=5)
    groq_max_output_tokens: int = Field(default=1024, ge=64, le=4096)

    # ── Domain & Citation Guardrails ─────────────────────────────────────────
    canonical_base_url: str = "https://eurekasolutions.in/Eureka2026/"
    contact_url: Optional[str] = None

    @field_validator("allowed_origins", mode="before")
    @classmethod
    def parse_origins(cls, v: Any) -> list[str]:
        """Parse comma-separated origin string or validate origin list."""
        if isinstance(v, str):
            items = [item.strip() for item in v.split(",") if item.strip()]
        elif isinstance(v, (list, set, tuple)):
            items = [str(item).strip() for item in v if str(item).strip()]
        else:
            items = []

        validated: list[str] = []
        for origin in items:
            parsed = urlparse(origin)
            if parsed.scheme not in ("http", "https") or not parsed.netloc:
                raise ValueError(
                    f"Invalid origin '{origin}'. Origins must include scheme (http/https) and host."
                )
            # Ensure no path or trailing slash in origin definition
            clean = f"{parsed.scheme}://{parsed.netloc}"
            if clean not in validated:
                validated.append(clean)
        return validated or ["http://localhost:3000", "https://eurekasolutions.in"]

    @field_validator("trusted_proxies", mode="before")
    @classmethod
    def parse_trusted_proxies(cls, v: Any) -> list[str]:
        """Parse comma-separated proxy list or collection of IPs."""
        if isinstance(v, str):
            return [ip.strip() for ip in v.split(",") if ip.strip()]
        if isinstance(v, (list, set, tuple)):
            return [str(ip).strip() for ip in v if str(ip).strip()]
        return []

    evidence_min_score: float = Field(default=0.45, ge=0.0, le=1.0)
    max_citations: int = Field(default=5, ge=1, le=10)
    allowed_citation_domains: tuple[str, ...] = ("eurekasolutions.in", "www.eurekasolutions.in")

    @property
    def environment(self) -> str:
        return self.app_env

    @property
    def vector_persist_directory(self) -> str:
        return self.chroma_persist_directory

    @property
    def vector_collection_name(self) -> str:
        return self.chroma_collection

    @property
    def embedding_model_name(self) -> str:
        return self.embedding_model

    @property
    def retrieval_top_k(self) -> int:
        return self.top_k

    @property
    def docs_enabled(self) -> bool:
        """Return whether interactive API docs (Swagger/ReDoc) should be active."""
        if self.enable_docs is not None:
            return self.enable_docs
        return self.app_env.lower() != "production"

    @property
    def enable_interactive_docs(self) -> bool:
        return self.docs_enabled


_app_settings_instance: Optional[AppSettings] = None


def get_app_settings(**overrides: Any) -> AppSettings:
    """Return application settings instance, applying optional runtime overrides."""
    global _app_settings_instance
    if overrides:
        return AppSettings(**overrides)
    if _app_settings_instance is None:
        _app_settings_instance = AppSettings()
    return _app_settings_instance
