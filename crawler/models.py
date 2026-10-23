"""
crawler/models.py
=================
Pydantic data models for the Eureka RAG Chatbot crawler (schema version 1.0).

Models are used for:
 1. Raw dataset root and page records  → data/raw/eureka_website_data.json
 2. Processed (chunked) dataset        → data/processed/eureka_website_chunks.json
 3. Internal pipeline intermediates
 4. Validation and report structures

Hard rules:
- Missing information is null / empty list — never invented.
- Serialisation is deterministic (model_config sort_keys where applicable).
- All models validate on instantiation; invalid records raise ValidationError.
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any, Literal, Optional

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


# ── Shared ────────────────────────────────────────────────────────────────────

def _utcnow_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


# ── URL / Discovery ───────────────────────────────────────────────────────────

class DiscoveredURL(BaseModel):
    """A URL discovered during crawl discovery."""

    model_config = ConfigDict(frozen=True)

    url: str
    normalized_url: str
    depth: int = 0
    source: str = "seed"  # "seed" | "sitemap" | "link" | "redirect"
    skip_reason: Optional[str] = None  # set when url is skipped


class FetchStatus(BaseModel):
    """Result of a single HTTP fetch attempt."""

    url: str
    final_url: str
    http_status: Optional[int] = None
    content_type: Optional[str] = None
    response_size_bytes: Optional[int] = None
    fetch_duration_seconds: Optional[float] = None
    error: Optional[str] = None
    was_retried: bool = False
    retry_count: int = 0
    skipped: bool = False
    skip_reason: Optional[str] = None
    blocked: bool = False
    block_reason: Optional[str] = None
    robots_disallowed: bool = False


# ── Heading ───────────────────────────────────────────────────────────────────

class Heading(BaseModel):
    """An extracted heading with level (1=H1, 2=H2, 3=H3)."""

    model_config = ConfigDict(frozen=True)

    level: int = Field(ge=1, le=6)
    text: str

    @field_validator("text")
    @classmethod
    def strip_text(cls, v: str) -> str:
        return v.strip()


# ── Content block ─────────────────────────────────────────────────────────────

class ContentBlock(BaseModel):
    """An optional structured content block extracted from the page."""

    block_type: str  # "paragraph" | "list" | "table" | "heading"
    heading_context: Optional[str] = None  # nearest preceding heading
    content: str

    @field_validator("block_type")
    @classmethod
    def validate_block_type(cls, v: str) -> str:
        allowed = {"paragraph", "list", "table", "heading", "text"}
        if v not in allowed:
            raise ValueError(f"block_type must be one of {allowed}, got {v!r}")
        return v


# ── Raw page record ───────────────────────────────────────────────────────────

class PageRecord(BaseModel):
    """A single crawled and extracted page record (schema version 1.0)."""

    model_config = ConfigDict(populate_by_name=True)

    # Identity
    page_id: str = Field(description="SHA-256 hex of normalised canonical/source URL")
    schema_version: str = Field(default="1.0")

    # URLs
    source_url: str = Field(description="Original requested URL")
    canonical_url: Optional[str] = Field(
        default=None, description="<link rel=canonical> href if present"
    )
    final_url: str = Field(description="Final URL after all redirects")

    # Content
    title: Optional[str] = None
    meta_description: Optional[str] = None
    headings: list[Heading] = Field(default_factory=list)
    content: str = Field(default="", description="Cleaned readable text content")
    content_blocks: list[ContentBlock] = Field(default_factory=list)
    internal_links: list[str] = Field(default_factory=list)

    # Integrity
    content_hash: str = Field(description="SHA-256 of normalised content+title")

    # Fetch metadata
    http_status: Optional[int] = None
    crawl_timestamp: str = Field(default_factory=_utcnow_iso)

    # Quality
    warnings: list[str] = Field(default_factory=list)
    is_low_content: bool = False
    is_empty: bool = False

    @field_validator("page_id", "content_hash")
    @classmethod
    def validate_hex_hash(cls, v: str) -> str:
        if len(v) != 64 or not all(c in "0123456789abcdef" for c in v):
            raise ValueError(f"Expected 64-char lowercase hex hash, got: {v!r}")
        return v

    @field_validator("schema_version")
    @classmethod
    def validate_schema_version(cls, v: str) -> str:
        if v != "1.0":
            raise ValueError(f"schema_version must be '1.0', got {v!r}")
        return v


# ── Raw dataset root ──────────────────────────────────────────────────────────

class CrawlStats(BaseModel):
    """Crawl outcome statistics."""

    discovered: int = 0
    attempted: int = 0
    succeeded: int = 0
    failed: int = 0
    skipped: int = 0
    blocked: int = 0
    out_of_scope: int = 0
    empty_or_low_content: int = 0
    duplicate_urls: int = 0
    duplicate_content: int = 0
    http_status_counts: dict[str, int] = Field(default_factory=dict)


class RawDataset(BaseModel):
    """Root envelope for data/raw/eureka_website_data.json."""

    schema_version: str = "1.0"
    run_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    crawler_version: str = "1.0.0"
    website_scope: str = "https://eurekasolutions.in/Eureka2026/"
    crawl_start: Optional[str] = None
    crawl_finish: Optional[str] = None
    duration_seconds: Optional[float] = None
    config_summary: dict[str, Any] = Field(default_factory=dict)
    is_complete: bool = False
    is_dry_run: bool = False
    is_fixture_run: bool = False
    stats: CrawlStats = Field(default_factory=CrawlStats)
    pages: list[PageRecord] = Field(default_factory=list)
    known_limitations: list[str] = Field(default_factory=list)

    @field_validator("schema_version")
    @classmethod
    def validate_schema_version(cls, v: str) -> str:
        if v != "1.0":
            raise ValueError(f"schema_version must be '1.0', got {v!r}")
        return v


# ── Chunk record ──────────────────────────────────────────────────────────────

class ChunkRecord(BaseModel):
    """A single token-aware chunk (schema version 1.0)."""

    model_config = ConfigDict(populate_by_name=True)

    # Identity
    chunk_id: str = Field(description="SHA-256 of page_id:chunk_index:chunking_version")
    page_id: str = Field(description="Parent page_id (hex)")
    chunk_index: int = Field(ge=0)

    # Provenance
    source_url: str
    canonical_url: Optional[str] = None
    page_title: Optional[str] = None
    section_heading: Optional[str] = None
    heading_path: list[str] = Field(default_factory=list)

    # Content
    content: str

    # Token integrity
    token_count: int = Field(ge=0)
    content_hash: str
    chunking_version: str = "1.0"

    # Optional ops metadata
    last_crawled_at: Optional[str] = None

    @field_validator("chunk_id", "content_hash")
    @classmethod
    def validate_hex_hash(cls, v: str) -> str:
        if len(v) != 64 or not all(c in "0123456789abcdef" for c in v):
            raise ValueError(f"Expected 64-char hex hash, got: {v!r}")
        return v

    @field_validator("content")
    @classmethod
    def content_not_empty(cls, v: str) -> str:
        if not v.strip():
            raise ValueError("chunk content must not be empty")
        return v


# ── Chunk dataset root ────────────────────────────────────────────────────────

class ChunkDataset(BaseModel):
    """Root envelope for data/processed/eureka_website_chunks.json."""

    schema_version: str = "1.0"
    run_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    crawler_version: str = "1.0.0"
    source_raw_run_id: Optional[str] = None
    source_raw_hash: Optional[str] = None
    chunking_config: dict[str, Any] = Field(default_factory=dict)
    created_at: str = Field(default_factory=_utcnow_iso)
    total_chunks: int = 0
    total_pages: int = 0
    chunks: list[ChunkRecord] = Field(default_factory=list)

    @field_validator("schema_version")
    @classmethod
    def validate_schema_version(cls, v: str) -> str:
        if v != "1.0":
            raise ValueError(f"schema_version must be '1.0', got {v!r}")
        return v

    @model_validator(mode="after")
    def sync_counts(self) -> "ChunkDataset":
        """Keep total_chunks consistent with actual list length."""
        if self.chunks:
            self.total_chunks = len(self.chunks)
        return self


# ── Validation results ────────────────────────────────────────────────────────

class ValidationIssue(BaseModel):
    """A single validation finding (error or warning)."""

    severity: Literal["error", "warning"]
    record_id: Optional[str] = None  # page_id or chunk_id, if applicable
    field: Optional[str] = None
    message: str


class ValidationReport(BaseModel):
    """Validation summary produced by validate_data."""

    dataset: str  # "raw" | "processed"
    schema_valid: bool = True
    total_records: int = 0
    error_count: int = 0
    warning_count: int = 0
    issues: list[ValidationIssue] = Field(default_factory=list)
    passed: bool = False

    @model_validator(mode="after")
    def set_passed(self) -> "ValidationReport":
        self.passed = self.schema_valid and self.error_count == 0
        return self
