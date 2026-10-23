"""
backend/retrieval/retriever.py
==============================
Production semantic retrieval engine for the Eureka RAG Chatbot.

Key features:
- Accepts raw user queries and applies identical preprocessing as the embedder.
- Retrieves top-k candidate chunks from the vector store using dense vector cosine search.
- Conservative deduplication:
  - Eliminates duplicate chunk IDs.
  - Limits excessive results from a single webpage (max_same_page_results, default 3)
    without starving retrieval if alternative pages are scarce.
- Supports optional similarity threshold filtering (disabled by default).
- Strictly preserves source attribution metadata (URL, page title, headings).
- Decoupled from LLMs: NO Groq calls, NO answer generation, NO prompt construction.
"""
from __future__ import annotations

import logging
import time
from typing import Any, Optional

from backend.config import BackendSettings, get_backend_settings
from backend.embeddings.base import BaseEmbedder
from backend.retrieval.models import RetrievalResponse, SearchResult
from backend.vectorstore.base import BaseVectorStore

logger = logging.getLogger(__name__)


class SemanticRetriever:
    """Retrieves relevant website chunks for user queries."""

    def __init__(
        self,
        vector_store: BaseVectorStore,
        embedder: BaseEmbedder,
        settings: Optional[BackendSettings] = None,
    ) -> None:
        self.vector_store = vector_store
        self.embedder = embedder
        self.settings = settings or get_backend_settings()

    def retrieve(
        self,
        query: str,
        top_k: Optional[int] = None,
        relevance_threshold: Optional[float] = None,
        max_same_page_results: Optional[int] = None,
        metadata_filter: Optional[dict[str, Any]] = None,
    ) -> RetrievalResponse:
        """Execute semantic retrieval for a user query."""
        start_time = time.perf_counter()

        k = top_k if top_k is not None else self.settings.top_k
        if k < 1 or k > 20:
            raise ValueError(f"top_k must be between 1 and 20, got {k}")

        threshold = (
            relevance_threshold
            if relevance_threshold is not None
            else self.settings.relevance_threshold
        )
        max_per_page = (
            max_same_page_results
            if max_same_page_results is not None
            else self.settings.max_same_page_results
        )

        clean_query = self.embedder.preprocess(query)
        if not clean_query:
            logger.debug("Received empty query, returning empty retrieval response.")
            return RetrievalResponse(
                query=query,
                top_k=k,
                total_results=0,
                results=[],
                duration_ms=round((time.perf_counter() - start_time) * 1000, 2),
            )

        # 1. Embed query vector
        try:
            query_embedding = self.embedder.embed_query(clean_query)
        except Exception as exc:
            logger.error("Failed to embed query: %s", exc)
            raise RuntimeError(f"Error computing query embedding: {exc}") from exc

        # 2. Query vector store with candidate headroom for deduplication
        candidate_k = min(max(k * 4, 24), 60)
        raw_results = self.vector_store.query(
            query_embedding=query_embedding,
            top_k=candidate_k,
            filter=metadata_filter,
        )

        # 3. Convert to project SearchResult models
        candidates = [SearchResult.from_vector_query_result(r) for r in raw_results]

        # 4. Filter by optional relevance threshold
        if threshold is not None:
            filtered: list[SearchResult] = []
            for c in candidates:
                if c.score is not None:
                    if c.score >= threshold:
                        filtered.append(c)
                else:
                    filtered.append(c)
            candidates = filtered

        # 5. Deduplicate and limit single-page concentration
        deduped_results: list[SearchResult] = []
        deferred_page_overflow: list[SearchResult] = []
        seen_chunk_ids: set[str] = set()
        page_counts: dict[str, int] = {}

        for c in candidates:
            if c.chunk_id in seen_chunk_ids:
                continue
            seen_chunk_ids.add(c.chunk_id)

            p_id = c.page_id or c.source_url
            current_page_count = page_counts.get(p_id, 0)
            if current_page_count < max_per_page:
                deduped_results.append(c)
                page_counts[p_id] = current_page_count + 1
                if len(deduped_results) >= k:
                    break
            else:
                deferred_page_overflow.append(c)

        # If we have not yet reached top_k, fill with deferred results rather than starving
        if len(deduped_results) < k and deferred_page_overflow:
            needed = k - len(deduped_results)
            deduped_results.extend(deferred_page_overflow[:needed])

        duration_ms = round((time.perf_counter() - start_time) * 1000, 2)
        logger.debug(
            "Retrieved %d results for query '%s' in %.2fms",
            len(deduped_results),
            clean_query,
            duration_ms,
        )

        return RetrievalResponse(
            query=query,
            top_k=k,
            total_results=len(deduped_results),
            results=deduped_results,
            duration_ms=duration_ms,
        )
