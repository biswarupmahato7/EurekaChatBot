"""
backend/retrieval/models.py
===========================
Data contracts for semantic retrieval queries and results.
"""
from __future__ import annotations

import json
from typing import Any, Optional

from pydantic import BaseModel, Field


class SearchResult(BaseModel):
    """A single retrieved chunk with source attribution and distance metrics."""

    chunk_id: str = Field(description="Stable chunk identifier")
    page_id: str = Field(description="Parent page identifier")
    text: str = Field(description="Extracted chunk text content")
    source_url: str = Field(description="Original website URL for the source page")
    page_title: str = Field(default="", description="Title of the source webpage")
    section_heading: str = Field(default="", description="Immediate section heading for chunk")
    heading_path: list[str] = Field(default_factory=list, description="Hierarchical heading path")
    score: Optional[float] = Field(default=None, description="Cosine similarity score (1 - distance)")
    distance: Optional[float] = Field(default=None, description="Raw distance metric from vector store")
    metadata: dict[str, Any] = Field(default_factory=dict, description="Additional chunk metadata")

    @classmethod
    def from_vector_query_result(cls, vqr: Any) -> SearchResult:
        """Construct SearchResult from a BaseVectorStore VectorQueryResult."""
        meta = dict(vqr.metadata or {})
        heading_path_val = meta.get("heading_path", [])
        if isinstance(heading_path_val, str) and heading_path_val.startswith("["):
            try:
                heading_path_val = json.loads(heading_path_val)
            except Exception:
                heading_path_val = [heading_path_val]
        elif not isinstance(heading_path_val, list):
            heading_path_val = [str(heading_path_val)] if heading_path_val else []

        return cls(
            chunk_id=str(meta.get("chunk_id", vqr.id)),
            page_id=str(meta.get("page_id", "")),
            text=vqr.document,
            source_url=str(meta.get("source_url", "")),
            page_title=str(meta.get("page_title", "")),
            section_heading=str(meta.get("section_heading", "")),
            heading_path=heading_path_val,
            score=vqr.score,
            distance=vqr.distance,
            metadata=meta,
        )


class RetrievalResponse(BaseModel):
    """Encapsulates the response from a semantic retrieval query."""

    query: str
    top_k: int
    total_results: int
    results: list[SearchResult]
    duration_ms: float = 0.0
