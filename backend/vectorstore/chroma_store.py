"""
backend/vectorstore/chroma_store.py
===================================
ChromaDB persistent vector store adapter for the Eureka RAG Chatbot.

Key features:
- Implements BaseVectorStore.
- Uses chromadb.PersistentClient for automatic on-disk persistence.
- Configures collection "eureka_website_chunks" with cosine distance metric.
- Strictly validates and flattens metadata into scalar types (str, int, float, bool).
- JSON-serializes complex fields like heading_path.
- Handles empty collections and query results gracefully.
- Provides close() method to flush and release SQLite file locks on Windows.
"""
from __future__ import annotations

import gc
import json
import logging
from pathlib import Path
from typing import Any, Optional

# Silence upstream posthog telemetry signature discrepancy in chromadb
try:
    import posthog

    posthog.capture = lambda *args, **kwargs: None
except Exception:
    pass

import chromadb
from chromadb.api.models.Collection import Collection

from backend.vectorstore.base import BaseVectorStore, VectorQueryResult, VectorRecord

logger = logging.getLogger(__name__)


def _sanitize_metadata_for_chroma(
    raw: dict[str, Any], record_id: str = ""
) -> dict[str, str | int | float | bool]:
    """Ensure all metadata values are primitive scalars supported by ChromaDB.

    ChromaDB metadata supports: str, int, float, bool.
    Complex structures (lists, dicts) are serialized to JSON strings.
    None values are dropped.
    ChromaDB requires non-empty metadata dicts when metadatas list is provided.
    """
    clean: dict[str, str | int | float | bool] = {}
    for k, v in raw.items():
        if v is None:
            continue
        if isinstance(v, (str, int, float, bool)):
            clean[k] = v
        elif isinstance(v, (list, dict)):
            clean[k] = json.dumps(v, ensure_ascii=False)
        else:
            clean[k] = str(v)

    # Ensure metadata is never completely empty to satisfy ChromaDB schema constraint
    if not clean:
        clean["id"] = record_id or "default"
    return clean


class ChromaVectorStore(BaseVectorStore):
    """Persistent ChromaDB implementation of BaseVectorStore."""

    def __init__(
        self,
        persist_directory: str | Path,
        collection_name: str = "eureka_website_chunks",
        distance_metric: str = "cosine",
    ) -> None:
        self.persist_directory = Path(persist_directory)
        self.persist_directory.mkdir(parents=True, exist_ok=True)
        self.collection_name = collection_name
        self.distance_metric = distance_metric

        logger.info(
            "Initializing ChromaDB PersistentClient at %s for collection %s",
            self.persist_directory,
            self.collection_name,
        )
        self._client: Optional[chromadb.PersistentClient] = chromadb.PersistentClient(
            path=str(self.persist_directory),
            settings=chromadb.config.Settings(anonymized_telemetry=False, is_persistent=True),
        )
        self._collection: Optional[Collection] = self._get_or_create_collection()

    def _get_or_create_collection(self) -> Collection:
        """Retrieve existing collection or create new one with configured distance metric."""
        assert self._client is not None, "Client has been closed"
        return self._client.get_or_create_collection(
            name=self.collection_name,
            metadata={"hnsw:space": self.distance_metric},
        )

    def count(self) -> int:
        """Return total number of records currently in the collection."""
        if self._collection is None:
            return 0
        return self._collection.count()

    def upsert(self, records: list[VectorRecord]) -> None:
        """Add or update vector records idempotently in batches."""
        if not records or self._collection is None:
            return

        ids: list[str] = []
        embeddings: list[list[float]] = []
        documents: list[str] = []
        metadatas: list[dict[str, str | int | float | bool]] = []

        for r in records:
            ids.append(r.id)
            embeddings.append(r.embedding)
            documents.append(r.document)
            metadatas.append(_sanitize_metadata_for_chroma(r.metadata, record_id=r.id))

        logger.debug("Upserting %d records into collection %s", len(records), self.collection_name)
        self._collection.upsert(
            ids=ids,
            embeddings=embeddings,
            documents=documents,
            metadatas=metadatas,
        )

    def query(
        self,
        query_embedding: list[float],
        top_k: int = 6,
        filter: Optional[dict[str, Any]] = None,
    ) -> list[VectorQueryResult]:
        """Query nearest neighbor records by embedding vector."""
        total = self.count()
        if total == 0 or self._collection is None:
            logger.debug("Collection is empty, returning empty query results.")
            return []

        n_results = min(top_k, total)
        query_kwargs: dict[str, Any] = {
            "query_embeddings": [query_embedding],
            "n_results": n_results,
            "include": ["documents", "metadatas", "distances"],
        }
        if filter:
            query_kwargs["where"] = filter

        res = self._collection.query(**query_kwargs)

        results: list[VectorQueryResult] = []
        raw_ids = res.get("ids")
        raw_docs = res.get("documents")
        raw_metas = res.get("metadatas")
        raw_dists = res.get("distances")

        res_ids = raw_ids[0] if (raw_ids is not None and len(raw_ids) > 0) else []
        res_docs = raw_docs[0] if (raw_docs is not None and len(raw_docs) > 0) else []
        res_metas = raw_metas[0] if (raw_metas is not None and len(raw_metas) > 0) else []
        res_dists = raw_dists[0] if (raw_dists is not None and len(raw_dists) > 0) else []

        for i, item_id in enumerate(res_ids):
            doc = res_docs[i] if i < len(res_docs) else ""
            meta = res_metas[i] if i < len(res_metas) else {}
            dist = float(res_dists[i]) if i < len(res_dists) and res_dists[i] is not None else None

            # For cosine distance (in [0, 2]), similarity score = 1.0 - distance
            score = (1.0 - dist) if (dist is not None and self.distance_metric == "cosine") else None

            results.append(
                VectorQueryResult(
                    id=item_id,
                    document=doc,
                    metadata=meta or {},
                    distance=dist,
                    score=score,
                )
            )

        return results

    def get(self, ids: list[str]) -> list[VectorRecord]:
        """Retrieve existing records by their IDs."""
        if not ids or self._collection is None:
            return []

        res = self._collection.get(
            ids=ids,
            include=["embeddings", "documents", "metadatas"],
        )
        records: list[VectorRecord] = []
        raw_ids = res.get("ids")
        raw_embeds = res.get("embeddings")
        raw_docs = res.get("documents")
        raw_metas = res.get("metadatas")

        res_ids = raw_ids if raw_ids is not None else []
        res_embeds = raw_embeds if raw_embeds is not None else []
        res_docs = raw_docs if raw_docs is not None else []
        res_metas = raw_metas if raw_metas is not None else []

        for i, item_id in enumerate(res_ids):
            emb = res_embeds[i] if i < len(res_embeds) else []
            doc = res_docs[i] if i < len(res_docs) else ""
            meta = res_metas[i] if i < len(res_metas) else {}

            emb_list: list[float] = []
            if emb is not None:
                try:
                    emb_list = list(emb)
                except Exception:
                    emb_list = []

            records.append(
                VectorRecord(
                    id=item_id,
                    embedding=emb_list,
                    document=doc,
                    metadata=meta or {},
                )
            )
        return records

    def delete(self, ids: list[str]) -> None:
        """Delete specific records by IDs."""
        if not ids or self._collection is None:
            return
        self._collection.delete(ids=ids)

    def reset(self) -> None:
        """Delete the collection and recreate a blank one."""
        if self._client is None:
            return
        logger.warning("Resetting collection %s", self.collection_name)
        try:
            self._client.delete_collection(self.collection_name)
        except Exception as exc:
            logger.debug("Exception during collection deletion (may not exist): %s", exc)
        self._collection = self._get_or_create_collection()

    def persist(self) -> None:
        """ChromaDB PersistentClient automatically persists state. Kept for interface compliance."""
        pass

    def close(self) -> None:
        """Release underlying client handles and clear system cache."""
        try:
            if self._client is not None:
                self._client.clear_system_cache()
            self._collection = None
            self._client = None
            gc.collect()
        except Exception as exc:
            logger.debug("Exception closing Chroma client: %s", exc)
