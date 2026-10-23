"""
backend/embeddings/sentence_transformer_embedder.py
===================================================
Production sentence-transformers embedding wrapper for Eureka RAG Chatbot.

Key features:
- Uses sentence-transformers/all-MiniLM-L6-v2 (CPU-optimized baseline, 384 dimensions).
- In-process singleton model caching to avoid reloading model weights on every query.
- Consistent text preprocessing applied to both documents and queries.
- L2-normalized embeddings for direct compatibility with cosine distance metric.
- Clear error handling for model loading and missing dependencies.
- Completely offline-compatible once weights are cached locally.
"""
from __future__ import annotations

import logging
from typing import Any, Optional

from backend.embeddings.base import BaseEmbedder

logger = logging.getLogger(__name__)


class SentenceTransformerEmbedder(BaseEmbedder):
    """Embedder implementation wrapping sentence-transformers with process-level model reuse."""

    # Class-level cache: {cache_key: model_instance}
    _model_cache: dict[str, Any] = {}

    def __init__(
        self,
        model_name: str = "sentence-transformers/all-MiniLM-L6-v2",
        device: str = "cpu",
        batch_size: int = 64,
        normalize_embeddings: bool = True,
        preprocessing_version: str = "1.0",
        lazy_load: bool = True,
    ) -> None:
        super().__init__()
        self._model_name = model_name
        self._dimension = 384
        self._device = device
        self.batch_size = batch_size
        self.normalize_embeddings = normalize_embeddings
        self._preprocessing_version = preprocessing_version
        self._model = None
        self._resolved_version = "unknown"
        if not lazy_load:
            self._model = self._load_or_get_cached_model()
            self._resolved_version = self._detect_model_version()

    @property
    def model(self) -> Any:
        """Return initialized SentenceTransformer instance, loading on-demand if deferred."""
        if self._model is None:
            self._model = self._load_or_get_cached_model()
            self._resolved_version = self._detect_model_version()
        return self._model

    @property
    def model_name(self) -> str:
        return self._model_name

    @property
    def dimension(self) -> int:
        return self._dimension

    @property
    def device(self) -> str:
        return self._device

    @property
    def preprocessing_version(self) -> str:
        return self._preprocessing_version

    def _load_or_get_cached_model(self) -> Any:
        """Load the model or reuse cached instance in memory."""
        cache_key = f"{self.model_name}::{self.device}"
        if cache_key in self._model_cache:
            logger.debug("Reusing cached SentenceTransformer model instance: %s", cache_key)
            return self._model_cache[cache_key]

        logger.info(
            "Loading SentenceTransformer model '%s' on device '%s'...",
            self.model_name,
            self.device,
        )
        try:
            from sentence_transformers import SentenceTransformer
        except ImportError as exc:
            raise ImportError(
                "sentence-transformers is not installed in the active environment. "
                "Install it using: pip install 'sentence-transformers>=3.0,<4.0'"
            ) from exc

        try:
            try:
                import torch
                torch.set_grad_enabled(False)
                torch.set_num_threads(1)
                try:
                    torch.set_num_interop_threads(1)
                except RuntimeError:
                    pass
            except Exception:
                pass

            model = SentenceTransformer(
                self.model_name,
                device=self.device,
                model_kwargs={"low_cpu_mem_usage": True},
            )
            model.eval()
            for param in model.parameters():
                param.requires_grad = False
            import gc
            gc.collect()

            # Verify actual dimension
            test_dim = model.get_sentence_embedding_dimension()
            if test_dim:
                self._dimension = int(test_dim)
            self._model_cache[cache_key] = model
            logger.info(
                "Successfully loaded model '%s' (embedding dimension: %d)",
                self.model_name,
                self.dimension,
            )
            return model
        except Exception as exc:
            logger.error("Failed to load SentenceTransformer model '%s': %s", self.model_name, exc)
            raise RuntimeError(
                f"Could not load embedding model '{self.model_name}'. "
                f"Ensure internet connectivity for initial download or provide cached weights: {exc}"
            ) from exc

    def _detect_model_version(self) -> str:
        """Detect and return model revision or package version."""
        try:
            import sentence_transformers

            return getattr(sentence_transformers, "__version__", "unknown")
        except Exception:
            return "unknown"

    @property
    def model_version(self) -> str:
        return self._resolved_version

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        """Embed a batch of document texts, applying uniform preprocessing."""
        if not texts:
            return []

        preprocessed = [self.preprocess(t) for t in texts]
        embeddings = self.model.encode(
            preprocessed,
            batch_size=self.batch_size,
            show_progress_bar=False,
            normalize_embeddings=self.normalize_embeddings,
            convert_to_numpy=True,
        )
        return [vec.tolist() for vec in embeddings]

    def embed_query(self, text: str) -> list[float]:
        """Embed a single search query, applying uniform preprocessing."""
        clean_text = self.preprocess(text)
        if not clean_text:
            raise ValueError("Query text cannot be empty or whitespace-only.")

        embedding = self.model.encode(
            clean_text,
            show_progress_bar=False,
            normalize_embeddings=self.normalize_embeddings,
            convert_to_numpy=True,
        )
        return embedding.tolist()

