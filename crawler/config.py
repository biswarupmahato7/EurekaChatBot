"""
crawler/config.py
=================
Validated Pydantic settings for the Eureka RAG Chatbot crawler.

A.0 Inspection findings recorded here:
- Live site: https://eurekasolutions.in/Eureka2026/
- Canonical URLs use the /Eureka2026/ prefix (e.g. /Eureka2026/services)
- Sitemap at: https://eurekasolutions.in/Eureka2026/sitemap.xml (103 URLs)
- All content pages are server-rendered HTML — no Playwright needed
- No robots.txt exists (404), so no crawl restrictions from robots
- Pages without /Eureka2026/ prefix return 404

Environment variables are loaded from .env (see .env.example for all options).
No Groq or embedding API key is required or loaded here.
"""
from __future__ import annotations

import logging
import os
from pathlib import Path
from typing import Any

from pydantic import AnyHttpUrl, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Project root — parent of the crawler/ directory
# ---------------------------------------------------------------------------
_PROJECT_ROOT = Path(__file__).parent.parent


class CrawlerSettings(BaseSettings):
    """Validated configuration for the Eureka RAG Chatbot crawler.

    All values can be overridden by environment variables (case-insensitive).
    Load from .env with python-dotenv.
    """

    model_config = SettingsConfigDict(
        env_file=str(_PROJECT_ROOT / ".env"),
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # ── Application ──────────────────────────────────────────────────────────
    app_env: str = "development"
    log_level: str = "INFO"

    # ── Crawler target ────────────────────────────────────────────────────────
    # Approved crawl origin and path prefix (A.0 confirmed).
    crawler_base_url: str = "https://eurekasolutions.in/Eureka2026/"
    crawler_approved_origin: str = "eurekasolutions.in"
    crawler_approved_path_prefix: str = "/Eureka2026/"
    # Sitemap location (confirmed at A.0)
    crawler_sitemap_url: str = (
        "https://eurekasolutions.in/Eureka2026/sitemap.xml"
    )

    # Extra allow-listed paths or origins (comma-separated). Empty = none.
    crawler_extra_allowed_paths: str = ""

    # Path patterns to exclude (comma-separated regex fragments).
    crawler_excluded_patterns: str = (
        "privacy-policy,terms-of-use,#,mailto:,tel:,javascript:"
    )

    # ── HTTP behaviour ────────────────────────────────────────────────────────
    crawler_user_agent: str = (
        "EurekaRAGBot/1.0 (+https://eurekasolutions.in; contact:info@eurekasolutions.in)"
    )
    crawler_request_timeout_seconds: int = 20
    crawler_request_delay_seconds: float = 1.5
    crawler_max_retries: int = 3
    crawler_max_response_bytes: int = 5_242_880  # 5 MB
    crawler_concurrency: int = 1  # Sequential — safe default

    # ── Crawl bounds ──────────────────────────────────────────────────────────
    crawler_max_pages: int = 150
    crawler_max_depth: int = 6

    # ── Chunking / tokenizer ──────────────────────────────────────────────────
    tokenizer: str = "cl100k_base"
    chunk_target_tokens: int = 500
    chunk_overlap_tokens: int = 75
    chunk_max_tokens: int = 700
    chunk_min_tokens: int = 80

    # ── Data paths ────────────────────────────────────────────────────────────
    raw_data_path: str = str(_PROJECT_ROOT / "data" / "raw" / "eureka_website_data.json")
    processed_data_path: str = str(
        _PROJECT_ROOT / "data" / "processed" / "eureka_website_chunks.json"
    )
    reports_path: str = str(_PROJECT_ROOT / "data" / "reports")
    checkpoints_path: str = str(_PROJECT_ROOT / "data" / "checkpoints")

    # ── Pipeline mode ─────────────────────────────────────────────────────────
    pipeline_mode: str = "full"  # "full" | "incremental"
    dry_run: bool = False

    # ── Versioning ────────────────────────────────────────────────────────────
    schema_version: str = "1.0"
    crawler_version: str = "1.0.0"
    chunking_version: str = "1.0"

    # ── Stale-page policy ─────────────────────────────────────────────────────
    # Number of consecutive confirmed 404/410 responses before a page is
    # marked stale and eligible for removal.
    stale_miss_threshold: int = 3

    # ═════════════════════════════════════════════════════════════════════════
    # Validators
    # ═════════════════════════════════════════════════════════════════════════

    @field_validator("log_level")
    @classmethod
    def validate_log_level(cls, v: str) -> str:
        valid = {"DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"}
        upper = v.upper()
        if upper not in valid:
            raise ValueError(f"log_level must be one of {valid}, got {v!r}")
        return upper

    @field_validator("pipeline_mode")
    @classmethod
    def validate_pipeline_mode(cls, v: str) -> str:
        valid = {"full", "incremental"}
        lower = v.lower()
        if lower not in valid:
            raise ValueError(f"pipeline_mode must be 'full' or 'incremental', got {v!r}")
        return lower

    @field_validator("tokenizer")
    @classmethod
    def validate_tokenizer(cls, v: str) -> str:
        allowed = {"cl100k_base", "p50k_base", "r50k_base", "gpt2", "p50k_edit"}
        if v not in allowed:
            raise ValueError(
                f"tokenizer must be one of {allowed}, got {v!r}. "
                "Check .env.example for documentation on consistent tokenizer use."
            )
        return v

    @field_validator("crawler_request_timeout_seconds")
    @classmethod
    def validate_timeout(cls, v: int) -> int:
        if not 1 <= v <= 120:
            raise ValueError(f"timeout must be 1–120s, got {v}")
        return v

    @field_validator("crawler_max_pages")
    @classmethod
    def validate_max_pages(cls, v: int) -> int:
        if not 1 <= v <= 10_000:
            raise ValueError(f"max_pages must be 1–10000, got {v}")
        return v

    @field_validator("crawler_max_depth")
    @classmethod
    def validate_max_depth(cls, v: int) -> int:
        if not 1 <= v <= 20:
            raise ValueError(f"max_depth must be 1–20, got {v}")
        return v

    @field_validator("crawler_request_delay_seconds")
    @classmethod
    def validate_delay(cls, v: float) -> float:
        if v < 0:
            raise ValueError(f"delay must be >= 0, got {v}")
        return v

    @field_validator("chunk_target_tokens", "chunk_overlap_tokens", "chunk_max_tokens", "chunk_min_tokens")
    @classmethod
    def validate_chunk_positive(cls, v: int) -> int:
        if v < 1:
            raise ValueError(f"chunk token values must be positive, got {v}")
        return v

    @model_validator(mode="after")
    def validate_chunk_relationships(self) -> "CrawlerSettings":
        if self.chunk_overlap_tokens >= self.chunk_target_tokens:
            raise ValueError(
                f"chunk_overlap_tokens ({self.chunk_overlap_tokens}) must be "
                f"less than chunk_target_tokens ({self.chunk_target_tokens})"
            )
        if self.chunk_target_tokens > self.chunk_max_tokens:
            raise ValueError(
                f"chunk_target_tokens ({self.chunk_target_tokens}) must be "
                f"<= chunk_max_tokens ({self.chunk_max_tokens})"
            )
        if self.chunk_min_tokens >= self.chunk_max_tokens:
            raise ValueError(
                f"chunk_min_tokens ({self.chunk_min_tokens}) must be "
                f"< chunk_max_tokens ({self.chunk_max_tokens})"
            )
        return self

    @model_validator(mode="after")
    def validate_concurrency(self) -> "CrawlerSettings":
        if not 1 <= self.crawler_concurrency <= 10:
            raise ValueError(
                f"crawler_concurrency must be 1–10, got {self.crawler_concurrency}. "
                "High concurrency is disrespectful to the target server."
            )
        return self

    # ═════════════════════════════════════════════════════════════════════════
    # Convenience helpers
    # ═════════════════════════════════════════════════════════════════════════

    @property
    def raw_data_path_obj(self) -> Path:
        return Path(self.raw_data_path)

    @property
    def processed_data_path_obj(self) -> Path:
        return Path(self.processed_data_path)

    @property
    def reports_path_obj(self) -> Path:
        return Path(self.reports_path)

    @property
    def checkpoints_path_obj(self) -> Path:
        return Path(self.checkpoints_path)

    @property
    def excluded_patterns_list(self) -> list[str]:
        return [p.strip() for p in self.crawler_excluded_patterns.split(",") if p.strip()]

    @property
    def extra_allowed_paths_list(self) -> list[str]:
        return [p.strip() for p in self.crawler_extra_allowed_paths.split(",") if p.strip()]

    def chunking_config_dict(self) -> dict[str, Any]:
        """Serialisable chunking config for embedding in dataset roots."""
        return {
            "tokenizer": self.tokenizer,
            "target_tokens": self.chunk_target_tokens,
            "overlap_tokens": self.chunk_overlap_tokens,
            "max_tokens": self.chunk_max_tokens,
            "min_tokens": self.chunk_min_tokens,
            "chunking_version": self.chunking_version,
        }

    def safe_config_summary(self) -> dict[str, Any]:
        """Return a config dict safe to log / embed in reports (no secrets)."""
        return {
            "app_env": self.app_env,
            "base_url": self.crawler_base_url,
            "approved_origin": self.crawler_approved_origin,
            "approved_path_prefix": self.crawler_approved_path_prefix,
            "sitemap_url": self.crawler_sitemap_url,
            "user_agent": self.crawler_user_agent,
            "timeout_seconds": self.crawler_request_timeout_seconds,
            "delay_seconds": self.crawler_request_delay_seconds,
            "max_retries": self.crawler_max_retries,
            "max_response_bytes": self.crawler_max_response_bytes,
            "concurrency": self.crawler_concurrency,
            "max_pages": self.crawler_max_pages,
            "max_depth": self.crawler_max_depth,
            "pipeline_mode": self.pipeline_mode,
            "dry_run": self.dry_run,
            "chunking": self.chunking_config_dict(),
            "schema_version": self.schema_version,
            "crawler_version": self.crawler_version,
        }


def get_settings(**overrides: Any) -> CrawlerSettings:
    """Return a CrawlerSettings instance, applying any keyword overrides."""
    return CrawlerSettings(**overrides)
