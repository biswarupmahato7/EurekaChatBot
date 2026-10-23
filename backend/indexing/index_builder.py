"""
backend/indexing/index_builder.py
=================================
Reproducible, batch-oriented index builder for the Eureka RAG Chatbot.

Key features:
- Reads and strictly validates Phase A chunk JSON dataset.
- Reuses BaseEmbedder (e.g. SentenceTransformerEmbedder or MockEmbedder).
- Idempotent: Skips embedding calculation for unchanged chunks using content hashes.
- Detects model/version changes and enforces controlled rebuilds.
- Operates in configurable batches to conserve memory.
- Atomic manifest updates after successful indexing.
- Produces a detailed IndexBuildReport saved to data/reports/.
"""
from __future__ import annotations

import hashlib
import json
import logging
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

from pydantic import BaseModel, Field

from backend.config import BackendSettings, get_backend_settings
from backend.embeddings.base import BaseEmbedder
from backend.indexing.manifest import IndexManifest, compute_file_sha256
from backend.vectorstore.base import BaseVectorStore, VectorRecord
from backend.vectorstore.chroma_store import ChromaVectorStore

logger = logging.getLogger(__name__)


class IndexBuildReport(BaseModel):
    """Detailed report generated upon completing an index build."""

    status: str = "SUCCESS"
    dataset_path: str
    dataset_sha256: str
    dataset_type: str = "production"
    collection_name: str
    embedding_model: str
    embedding_dimension: int
    rebuild_forced: bool = False
    dry_run: bool = False
    total_input_chunks: int = 0
    valid_chunks: int = 0
    invalid_chunks: int = 0
    added_chunks: int = 0
    updated_chunks: int = 0
    skipped_chunks: int = 0
    embeddings_calculated: int = 0
    final_collection_count: int = 0
    duration_seconds: float = 0.0
    errors: list[str] = Field(default_factory=list)
    timestamp: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())


class IndexBuilder:
    """Orchestrates indexing of Phase A chunk datasets into the vector store."""

    def __init__(
        self,
        vector_store: BaseVectorStore,
        embedder: BaseEmbedder,
        settings: Optional[BackendSettings] = None,
        manifest_path: Optional[Path | str] = None,
    ) -> None:
        self.vector_store = vector_store
        self.embedder = embedder
        self.settings = settings or get_backend_settings()

        if manifest_path is None:
            self.manifest_path = self.settings.persist_dir_path / "index_manifest.json"
        else:
            self.manifest_path = Path(manifest_path)

    def build_index(
        self,
        chunks_file_path: Optional[Path | str] = None,
        batch_size: Optional[int] = None,
        rebuild: bool = False,
        dry_run: bool = False,
    ) -> IndexBuildReport:
        """Run the index construction or incremental update."""
        start_time = time.time()
        file_path = Path(chunks_file_path or self.settings.processed_data_path)
        batch_size = batch_size or self.settings.embedding_batch_size

        logger.info(
            "Starting index build (file=%s, batch_size=%d, rebuild=%s, dry_run=%s)",
            file_path,
            batch_size,
            rebuild,
            dry_run,
        )

        report = IndexBuildReport(
            dataset_path=str(file_path),
            dataset_sha256=compute_file_sha256(file_path),
            collection_name=self.settings.chroma_collection,
            embedding_model=self.embedder.model_name,
            embedding_dimension=self.embedder.dimension,
            rebuild_forced=rebuild,
            dry_run=dry_run,
        )

        if not file_path.exists():
            msg = f"Input chunks dataset file does not exist: {file_path}"
            logger.error(msg)
            report.status = "FAILED"
            report.errors.append(msg)
            report.duration_seconds = round(time.time() - start_time, 2)
            return report

        # Load raw chunk JSON
        try:
            with open(file_path, "r", encoding="utf-8") as f:
                raw_data = json.load(f)
        except Exception as exc:
            msg = f"Failed to parse chunk JSON: {exc}"
            logger.error(msg)
            report.status = "FAILED"
            report.errors.append(msg)
            report.duration_seconds = round(time.time() - start_time, 2)
            return report

        chunks_list: list[dict[str, Any]] = []
        if isinstance(raw_data, list):
            chunks_list = raw_data
        elif isinstance(raw_data, dict):
            # Check for fixture or production wrapper
            if "dataset_type" in raw_data:
                report.dataset_type = raw_data["dataset_type"]
            chunks_list = raw_data.get("chunks", [])
        else:
            msg = f"Invalid chunk data format: expected list or dict, got {type(raw_data)}"
            report.status = "FAILED"
            report.errors.append(msg)
            report.duration_seconds = round(time.time() - start_time, 2)
            return report

        # Detect fixture labeling if in path or content
        if "fixture" in str(file_path).lower():
            report.dataset_type = "fixture"

        report.total_input_chunks = len(chunks_list)
        logger.info("Loaded %d input chunks from %s", len(chunks_list), file_path)

        # 1. Validate chunks
        valid_chunks, invalid_errors = self._validate_chunks(chunks_list)
        report.valid_chunks = len(valid_chunks)
        report.invalid_chunks = len(invalid_errors)
        report.errors.extend(invalid_errors)

        if invalid_errors:
            logger.warning("Found %d invalid chunks during validation", len(invalid_errors))

        if dry_run:
            logger.info("Dry-run requested: skipping vector store writes.")
            report.status = "DRY_RUN"
            report.final_collection_count = self.vector_store.count()
            report.duration_seconds = round(time.time() - start_time, 2)
            return report

        # 2. Check manifest for model compatibility and incremental tracking
        manifest = IndexManifest.load(self.manifest_path)
        existing_hashes: dict[str, str] = {}

        if manifest:
            if not manifest.is_compatible(
                self.embedder.model_name,
                self.embedder.dimension,
                self.settings.preprocessing_version,
            ):
                logger.warning(
                    "Existing index manifest is incompatible with current embedder (%s, dim=%d) "
                    "vs target (%s, dim=%d). Forcing full rebuild to avoid vector space contamination.",
                    manifest.embedding_model,
                    manifest.embedding_dimension,
                    self.embedder.model_name,
                    self.embedder.dimension,
                )
                rebuild = True
            elif not rebuild:
                existing_hashes = dict(manifest.chunk_hashes)

        # 3. Categorize chunks: unchanged vs needs embedding / updating
        to_embed: list[dict[str, Any]] = []
        new_hashes: dict[str, str] = dict(existing_hashes) if not rebuild else {}

        for chunk in valid_chunks:
            c_id = chunk["chunk_id"]
            c_hash = chunk["content_hash"]
            if (not rebuild) and (c_id in existing_hashes) and (existing_hashes[c_id] == c_hash):
                report.skipped_chunks += 1
            else:
                to_embed.append(chunk)

        logger.info(
            "Indexing plan: %d chunks to process (%d unchanged chunks skipped)",
            len(to_embed),
            report.skipped_chunks,
        )

        # 4. Batch embed and prepare records
        # If rebuilding, compute embeddings first so a failure partway does not corrupt or wipe
        # the recoverable existing collection (INDEX-012).
        prepared_batches: list[list[VectorRecord]] = []
        for i in range(0, len(to_embed), batch_size):
            batch = to_embed[i : i + batch_size]
            texts = [c["text"] for c in batch]
            try:
                embeddings = self.embedder.embed_documents(texts)
                report.embeddings_calculated += len(embeddings)
            except Exception as exc:
                msg = f"Embedding batch failed at index {i}: {exc}"
                logger.error(msg)
                report.status = "FAILED"
                report.errors.append(msg)
                report.duration_seconds = round(time.time() - start_time, 2)
                return report

            records: list[VectorRecord] = []
            for j, c in enumerate(batch):
                c_id = c["chunk_id"]
                c_hash = c["content_hash"]
                emb = embeddings[j]

                # Prepare metadata preserving all Phase A contracts
                meta = {
                    "chunk_id": c_id,
                    "page_id": c.get("page_id", ""),
                    "source_url": c.get("source_url", ""),
                    "page_title": c.get("page_title", ""),
                    "section_heading": c.get("section_heading", ""),
                    "heading_path": c.get("heading_path", []),
                    "chunk_index": c.get("chunk_index", 0),
                    "token_count": c.get("token_count", 0),
                    "content_hash": c_hash,
                    "chunking_version": c.get("chunking_version", "1.0"),
                    "index_version": self.settings.index_version,
                }
                records.append(
                    VectorRecord(
                        id=c_id,
                        embedding=emb,
                        document=c["text"],
                        metadata=meta,
                    )
                )

                if c_id in existing_hashes and not rebuild:
                    report.updated_chunks += 1
                else:
                    report.added_chunks += 1
                new_hashes[c_id] = c_hash

            prepared_batches.append(records)

        # Reset collection only AFTER embeddings have succeeded (preserves data if embedding fails)
        if rebuild:
            logger.info("Embeddings succeeded. Resetting collection for clean rebuild.")
            self.vector_store.reset()

        for i, records in enumerate(prepared_batches):
            try:
                self.vector_store.upsert(records)
            except Exception as exc:
                msg = f"Vector store upsert failed at batch {i}: {exc}"
                logger.error(msg)
                report.status = "FAILED"
                report.errors.append(msg)
                report.duration_seconds = round(time.time() - start_time, 2)
                return report

        # Flush / persist
        self.vector_store.persist()
        report.final_collection_count = self.vector_store.count()

        # 5. Save updated manifest
        updated_manifest = IndexManifest(
            collection_name=self.settings.chroma_collection,
            embedding_model=self.embedder.model_name,
            embedding_dimension=self.embedder.dimension,
            model_version=getattr(self.embedder, "model_version", "1.0"),
            preprocessing_version=self.settings.preprocessing_version,
            index_version=self.settings.index_version,
            dataset_path=str(file_path),
            dataset_sha256=report.dataset_sha256,
            dataset_type=report.dataset_type,
            total_input_chunks=report.total_input_chunks,
            total_indexed_chunks=report.final_collection_count,
            chunk_hashes=new_hashes,
        )
        updated_manifest.save(self.manifest_path)

        report.duration_seconds = round(time.time() - start_time, 2)
        logger.info(
            "Index build finished successfully: count=%d (added=%d, updated=%d, skipped=%d, elapsed=%.2fs)",
            report.final_collection_count,
            report.added_chunks,
            report.updated_chunks,
            report.skipped_chunks,
            report.duration_seconds,
        )

        # Save build report to reports directory
        self._save_report(report)
        return report

    def _validate_chunks(
        self, chunks: list[dict[str, Any]]
    ) -> tuple[list[dict[str, Any]], list[str]]:
        """Validate input chunks against Phase A schema requirements."""
        valid: list[dict[str, Any]] = []
        errors: list[str] = []
        seen_ids: set[str] = set()

        for idx, c in enumerate(chunks):
            if not isinstance(c, dict):
                errors.append(f"Chunk at index {idx} is not a JSON object")
                continue

            # Phase A schema uses 'content' for chunk text; support both 'text' and 'content'
            text = str(c.get("text") or c.get("content") or "").strip()
            c["text"] = text

            if not c.get("chunk_id"):
                errors.append(f"Chunk index {idx} has missing or empty chunk_id")
                continue

            c_id = str(c["chunk_id"]).strip()
            if not c_id:
                errors.append(f"Chunk index {idx} has empty chunk_id")
                continue

            if not c.get("page_id"):
                errors.append(f"Chunk index {idx} has missing or empty page_id")
                continue

            if not c.get("source_url"):
                errors.append(f"Chunk index {idx} has missing or empty source_url")
                continue

            if c_id in seen_ids:
                errors.append(f"Duplicate chunk_id detected: {c_id}")
                continue
            seen_ids.add(c_id)

            if not text:
                errors.append(f"Chunk {c_id} has empty document text")
                continue

            # Ensure content_hash exists; if missing, calculate sha256
            if not c.get("content_hash"):
                c["content_hash"] = hashlib.sha256(text.encode("utf-8")).hexdigest()

            valid.append(c)

        return valid, errors

    def _save_report(self, report: IndexBuildReport) -> None:
        """Save JSON build report to data/reports/."""
        reports_dir = self.settings.reports_dir_path
        reports_dir.mkdir(parents=True, exist_ok=True)
        report_file = reports_dir / "index_build_report.json"
        try:
            with open(report_file, "w", encoding="utf-8") as f:
                f.write(report.model_dump_json(indent=2))
            logger.info("Saved index build report to %s", report_file)
        except Exception as exc:
            logger.warning("Could not save index build report to %s: %s", report_file, exc)
