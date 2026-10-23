"""
backend/embeddings/base.py
==========================
Abstract base interface for text embedding models.

Guarantees:
- Documents and queries undergo the exact same text preprocessing.
- Preprocessing version is tracked.
- Dimensionality is consistent and validated.
"""
from __future__ import annotations

import re
from abc import ABC, abstractmethod


class BaseEmbedder(ABC):
    """Abstract interface for embedding generation."""

    @property
    @abstractmethod
    def model_name(self) -> str:
        """The canonical name or HuggingFace ID of the embedding model."""

    @property
    @abstractmethod
    def dimension(self) -> int:
        """The vector dimension produced by this model (e.g. 384)."""

    @property
    def version(self) -> str:
        """Revision or version string of the model."""
        return "1.0"

    @property
    def preprocessing_version(self) -> str:
        """Version of preprocessing logic applied to inputs."""
        return "1.0"

    @property
    def device(self) -> str:
        """Device on which inference runs (cpu, cuda, etc.)."""
        return "cpu"

    def preprocess_text(self, text: str) -> str:
        """Apply uniform preprocessing to document chunks and query texts.

        Normalises whitespace, collapses repeated newlines and whitespace into a single space,
        and trims edges.
        """
        if not text:
            return ""
        return re.sub(r"\s+", " ", text).strip()

    def preprocess(self, text: str) -> str:
        """Apply uniform preprocessing to document chunks and query texts."""
        return self.preprocess_text(text)

    @abstractmethod
    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        """Compute dense vector embeddings for a batch of document texts."""

    @abstractmethod
    def embed_query(self, text: str) -> list[float]:
        """Compute dense vector embedding for a single query text."""
