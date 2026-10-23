"""
backend/config.py
=================
Validated Pydantic settings for the Eureka RAG Chatbot backend retrieval layer.

Loads environment variables from .env with sensible defaults.
No Groq or LLM API keys are required for Phase B.
"""
from __future__ import annotations

import logging
from pathlib import Path
from typing import Any, Optional

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

logger = logging.getLogger(__name__)

_PROJECT_ROOT = Path(__file__).parent.parent


class BackendSettings(BaseSettings):
    """Validated settings for Phase B retrieval foundation."""

    model_config = SettingsConfigDict(
        env_file=str(_PROJECT_ROOT / ".env"),
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # ── Application ──────────────────────────────────────────────────────────
    app_env: str = "development"
    log_level: str = "INFO"

    # ── Vector Store ─────────────────────────────────────────────────────────
    vector_store: str = "chroma"
    chroma_persist_directory: str = str(_PROJECT_ROOT / "data" / "vectorstore")
    chroma_collection: str = "eureka_website_chunks"

    # ── Embeddings ───────────────────────────────────────────────────────────
    embedding_model: str = "sentence-transformers/all-MiniLM-L6-v2"
    embedding_dimension: int = 384
    embedding_batch_size: int = 64
    embedding_device: str = "cpu"
    preprocessing_version: str = "1.0"
    index_version: str = "1.0"

    # ── Retrieval ────────────────────────────────────────────────────────────
    top_k: int = Field(default=6, ge=1, le=20)
    relevance_threshold: Optional[float] = None
    max_same_page_results: int = Field(default=2, ge=1, le=10)

    # ── Data Paths ───────────────────────────────────────────────────────────
    processed_data_path: str = str(
        _PROJECT_ROOT / "data" / "processed" / "eureka_website_chunks.json"
    )
    raw_data_path: str = str(_PROJECT_ROOT / "data" / "raw" / "eureka_website_data.json")
    reports_path: str = str(_PROJECT_ROOT / "data" / "reports")

    @field_validator("relevance_threshold", mode="before")
    @classmethod
    def parse_optional_threshold(cls, v: Any) -> Optional[float]:
        if v is None or v == "" or str(v).strip().lower() in ("none", "null", "configure_after_evaluation"):
            return None
        return float(v)

    @property
    def persist_dir_path(self) -> Path:
        return Path(self.chroma_persist_directory)

    @property
    def chunks_file_path(self) -> Path:
        return Path(self.processed_data_path)

    @property
    def reports_dir_path(self) -> Path:
        return Path(self.reports_path)


_settings_instance: Optional[BackendSettings] = None


def get_backend_settings(**overrides: Any) -> BackendSettings:
    """Return backend settings, applying optional runtime overrides."""
    global _settings_instance
    if overrides:
        return BackendSettings(**overrides)
    if _settings_instance is None:
        _settings_instance = BackendSettings()
    return _settings_instance
