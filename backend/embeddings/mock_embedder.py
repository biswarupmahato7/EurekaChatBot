"""
backend/embeddings/mock_embedder.py
==================================
Deterministic fake embedder for 100% offline unit and integration tests.

Produces consistent unit-length float vectors based on SHA-256 hashes of text.
Never downloads models or requires PyTorch/GPU.
"""
from __future__ import annotations

import hashlib
import math
from typing import Optional

from backend.embeddings.base import BaseEmbedder


class MockEmbedder(BaseEmbedder):
    """Deterministic offline embedder for tests."""

    def __init__(
        self,
        dimension: int = 384,
        model_name: str = "mock-embedder/all-MiniLM-L6-v2",
        version: str = "mock-1.0",
    ) -> None:
        self._dimension = dimension
        self._model_name = model_name
        self._version = version

    @property
    def model_name(self) -> str:
        return self._model_name

    @property
    def dimension(self) -> int:
        return self._dimension

    @property
    def version(self) -> str:
        return self._version

    def _hash_to_vector(self, text: str) -> list[float]:
        """Convert string to a deterministic unit-normalized float vector."""
        text_clean = self.preprocess_text(text)
        if not text_clean:
            # Deterministic representation for empty/zero input
            return [0.0] * self._dimension

        vec = []
        seed = text_clean.encode("utf-8")
        # Generate sufficient pseudo-random bytes deterministically via chaining SHA-256
        block = seed
        while len(vec) < self._dimension:
            digest = hashlib.sha256(block).digest()
            for b in digest:
                # Map byte 0..255 to -1.0 .. 1.0
                vec.append((b - 128.0) / 128.0)
                if len(vec) == self._dimension:
                    break
            block = digest + seed

        # L2-normalize vector to unit length
        norm = math.sqrt(sum(x * x for x in vec))
        if norm > 0:
            vec = [x / norm for x in vec]
        return vec

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        return [self._hash_to_vector(t) for t in texts]

    def embed_query(self, text: str) -> list[float]:
        clean = self.preprocess(text)
        if not clean:
            raise ValueError("Query text cannot be empty or whitespace-only.")
        return self._hash_to_vector(clean)

