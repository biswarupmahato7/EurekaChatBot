"""
backend/indexing/manifest.py
============================
Index manifest tracking embedding configuration, source dataset hashes, and chunk records.

Ensures:
- Safe reindexing: prevents mixing vectors from incompatible models/dimensions.
- Content hash tracking: enables skipping unchanged chunks during incremental runs.
- Full provenance: records dataset SHA-256, build timestamps, and model versions.
"""
from __future__ import annotations

import hashlib
import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)


def compute_file_sha256(path: Path | str) -> str:
    """Compute SHA-256 checksum of a file."""
    p = Path(path)
    if not p.exists():
        return ""
    hasher = hashlib.sha256()
    with open(p, "rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            hasher.update(chunk)
    return hasher.hexdigest()


class IndexManifest(BaseModel):
    """Provenance and compatibility metadata for a persistent vector collection."""

    manifest_version: str = "1.0"
    collection_name: str = "eureka_website_chunks"
    embedding_model: str
    embedding_dimension: int
    model_version: str = "unknown"
    preprocessing_version: str = "1.0"
    index_version: str = "1.0"
    dataset_path: str
    dataset_sha256: str
    dataset_type: str = "production"  # 'production' or 'fixture'
    total_input_chunks: int = 0
    total_indexed_chunks: int = 0
    last_built_at: str = Field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )
    # chunk_id -> content_hash mapping for incremental skip detection
    chunk_hashes: dict[str, str] = Field(default_factory=dict)

    def is_compatible(
        self,
        model_name: str,
        dimension: int,
        preprocessing_version: str = "1.0",
    ) -> bool:
        """Check if the existing index is compatible with the target embedding configuration."""
        return (
            self.embedding_model == model_name
            and self.embedding_dimension == dimension
            and self.preprocessing_version == preprocessing_version
        )

    def save(self, filepath: Path | str) -> None:
        """Persist manifest to JSON file atomically."""
        p = Path(filepath)
        p.parent.mkdir(parents=True, exist_ok=True)
        temp_p = p.with_suffix(".tmp")
        with open(temp_p, "w", encoding="utf-8") as f:
            f.write(self.model_dump_json(indent=2))
        temp_p.replace(p)
        logger.debug("Saved index manifest to %s", p)

    @classmethod
    def load(cls, filepath: Path | str) -> Optional[IndexManifest]:
        """Load manifest from JSON file if it exists, else return None."""
        p = Path(filepath)
        if not p.exists():
            return None
        try:
            with open(p, "r", encoding="utf-8") as f:
                data = json.load(f)
            return cls.model_validate(data)
        except Exception as exc:
            logger.warning("Could not load index manifest at %s: %s", p, exc)
            return None
