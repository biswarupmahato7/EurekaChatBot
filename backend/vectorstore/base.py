"""
backend/vectorstore/base.py
===========================
Abstract vector store interface and data models for semantic retrieval.

Design principles:
- Backend-only interface.
- Completely decoupled from specific vector database libraries.
- All stored records and query results use strongly typed Pydantic models.
- Metadata is strictly primitive-serializable (str, int, float, bool) to ensure
  safe compatibility with vector store metadata storage.
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any, Optional

from pydantic import BaseModel, Field


class VectorRecord(BaseModel):
    """A record to be added or upserted into the vector store."""

    id: str = Field(description="Unique stable record identifier, e.g. chunk_id")
    embedding: list[float] = Field(description="Dense vector embedding")
    document: str = Field(description="Original document or chunk text content")
    metadata: dict[str, Any] = Field(
        default_factory=dict,
        description="Flat metadata mapping with scalar values (str, int, float, bool)",
    )


class VectorQueryResult(BaseModel):
    """A single matched result from a vector query."""

    id: str = Field(description="Matched vector record ID")
    document: str = Field(description="Matched document content")
    metadata: dict[str, Any] = Field(default_factory=dict, description="Associated metadata")
    distance: Optional[float] = Field(default=None, description="Vector space distance metric")
    score: Optional[float] = Field(default=None, description="Similarity score (e.g. 1 - cosine distance)")


class BaseVectorStore(ABC):
    """Abstract interface for backend vector stores."""

    @abstractmethod
    def upsert(self, records: list[VectorRecord]) -> None:
        """Add or update vector records idempotently."""

    @abstractmethod
    def query(
        self,
        query_embedding: list[float],
        top_k: int = 6,
        filter: Optional[dict[str, Any]] = None,
    ) -> list[VectorQueryResult]:
        """Query nearest neighbor records by embedding vector."""

    @abstractmethod
    def get(self, ids: list[str]) -> list[VectorRecord]:
        """Retrieve existing records by their IDs."""

    @abstractmethod
    def count(self) -> int:
        """Return total number of records currently stored."""

    @abstractmethod
    def delete(self, ids: list[str]) -> None:
        """Delete specific records by IDs."""

    @abstractmethod
    def reset(self) -> None:
        """Delete all records in the collection / reset collection."""

    @abstractmethod
    def persist(self) -> None:
        """Ensure all writes are flushed and committed to disk."""
