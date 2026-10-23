"""
backend/tests/test_indexing.py
==============================
Tests for IndexBuilder, manifest generation, idempotency, and reindexing.
"""
from __future__ import annotations

import gc
import json
import tempfile
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from backend.config import get_backend_settings
from backend.embeddings.mock_embedder import MockEmbedder
from backend.indexing.index_builder import IndexBuilder
from backend.indexing.manifest import IndexManifest
from backend.vectorstore.chroma_store import ChromaVectorStore

FIXTURES_DIR = Path(__file__).parent / "fixtures"
SAMPLE_CHUNKS_PATH = FIXTURES_DIR / "sample_chunks.json"


@pytest.fixture
def temp_environment():
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmpdir:
        tmp_path = Path(tmpdir)
        store = ChromaVectorStore(persist_directory=tmp_path / "vectorstore", collection_name="test_chunks")
        manifest_path = tmp_path / "vectorstore" / "index_manifest.json"
        embedder = MockEmbedder(dimension=384)
        yield {
            "root": tmp_path,
            "store": store,
            "manifest_path": manifest_path,
            "embedder": embedder,
        }
        store.close()
        gc.collect()


def test_build_index_from_sample_chunks(temp_environment):
    store = temp_environment["store"]
    embedder = temp_environment["embedder"]
    manifest_path = temp_environment["manifest_path"]

    builder = IndexBuilder(
        vector_store=store,
        embedder=embedder,
        manifest_path=manifest_path,
    )

    report = builder.build_index(chunks_file_path=SAMPLE_CHUNKS_PATH, batch_size=2)
    assert report.status == "SUCCESS"
    assert report.total_input_chunks == 4
    assert report.valid_chunks == 4
    assert report.invalid_chunks == 0
    assert report.added_chunks == 4
    assert report.skipped_chunks == 0
    assert report.final_collection_count == 4
    assert store.count() == 4

    # Verify manifest
    manifest = IndexManifest.load(manifest_path)
    assert manifest is not None
    assert manifest.total_indexed_chunks == 4
    assert len(manifest.chunk_hashes) == 4


def test_repeated_build_skips_unchanged_chunks(temp_environment):
    store = temp_environment["store"]
    embedder = temp_environment["embedder"]
    manifest_path = temp_environment["manifest_path"]

    builder = IndexBuilder(vector_store=store, embedder=embedder, manifest_path=manifest_path)

    # Initial build
    report1 = builder.build_index(chunks_file_path=SAMPLE_CHUNKS_PATH)
    assert report1.added_chunks == 4
    assert report1.skipped_chunks == 0

    # Second build with unchanged dataset
    report2 = builder.build_index(chunks_file_path=SAMPLE_CHUNKS_PATH)
    assert report2.added_chunks == 0
    assert report2.updated_chunks == 0
    assert report2.skipped_chunks == 4
    assert report2.embeddings_calculated == 0
    assert store.count() == 4


def test_rebuild_flag_forces_full_reindex(temp_environment):
    store = temp_environment["store"]
    embedder = temp_environment["embedder"]
    manifest_path = temp_environment["manifest_path"]

    builder = IndexBuilder(vector_store=store, embedder=embedder, manifest_path=manifest_path)

    # Initial build
    builder.build_index(chunks_file_path=SAMPLE_CHUNKS_PATH)

    # Rebuild
    report_rebuild = builder.build_index(chunks_file_path=SAMPLE_CHUNKS_PATH, rebuild=True)
    assert report_rebuild.rebuild_forced is True
    assert report_rebuild.added_chunks == 4
    assert report_rebuild.skipped_chunks == 0
    assert store.count() == 4


def test_content_change_triggers_reembedding(temp_environment):
    store = temp_environment["store"]
    embedder = temp_environment["embedder"]
    manifest_path = temp_environment["manifest_path"]
    root = temp_environment["root"]

    builder = IndexBuilder(vector_store=store, embedder=embedder, manifest_path=manifest_path)
    builder.build_index(chunks_file_path=SAMPLE_CHUNKS_PATH)

    # Modify content of chunk 1 in a temporary file
    with open(SAMPLE_CHUNKS_PATH, "r", encoding="utf-8") as f:
        chunks = json.load(f)

    chunks[0]["content"] = "Completely altered new content for chunk 1."
    chunks[0]["content_hash"] = "new_hash_9999"

    mod_file = root / "modified_chunks.json"
    with open(mod_file, "w", encoding="utf-8") as f:
        json.dump(chunks, f)

    # Run incremental build
    report = builder.build_index(chunks_file_path=mod_file)
    assert report.updated_chunks == 1
    assert report.skipped_chunks == 3
    assert store.count() == 4


def test_invalid_chunks_rejected_and_reported(temp_environment):
    store = temp_environment["store"]
    embedder = temp_environment["embedder"]
    manifest_path = temp_environment["manifest_path"]
    root = temp_environment["root"]

    invalid_data = [
        {"chunk_id": "", "page_id": "p1", "text": "Valid text", "source_url": "https://example.com"},  # empty id
        {"chunk_id": "c2", "page_id": "p1", "text": "", "source_url": "https://example.com"},          # empty text
        {"chunk_id": "c3", "page_id": "", "text": "Valid text", "source_url": "https://example.com"},  # missing page_id
        {"chunk_id": "c4", "page_id": "p1", "text": "Valid text", "source_url": "https://example.com"},# valid
        {"chunk_id": "c4", "page_id": "p1", "text": "Duplicate chunk ID", "source_url": "https://example.com"}, # dup
    ]
    invalid_file = root / "invalid_chunks.json"
    with open(invalid_file, "w", encoding="utf-8") as f:
        json.dump(invalid_data, f)

    builder = IndexBuilder(vector_store=store, embedder=embedder, manifest_path=manifest_path)
    report = builder.build_index(chunks_file_path=invalid_file)

    assert report.total_input_chunks == 5
    assert report.valid_chunks == 1
    assert report.invalid_chunks == 4
    assert store.count() == 1


def test_model_change_triggers_safe_rebuild(temp_environment):
    store = temp_environment["store"]
    manifest_path = temp_environment["manifest_path"]

    embedder_v1 = MockEmbedder(model_name="model-v1", dimension=384)
    builder1 = IndexBuilder(vector_store=store, embedder=embedder_v1, manifest_path=manifest_path)
    builder1.build_index(chunks_file_path=SAMPLE_CHUNKS_PATH)

    # Switch to different model name
    embedder_v2 = MockEmbedder(model_name="model-v2-different", dimension=384)
    builder2 = IndexBuilder(vector_store=store, embedder=embedder_v2, manifest_path=manifest_path)

    # Incremental call without explicit rebuild flag should detect incompatibility and auto-rebuild
    report = builder2.build_index(chunks_file_path=SAMPLE_CHUNKS_PATH)
    assert report.status == "SUCCESS"
    assert report.added_chunks == 4
    assert report.skipped_chunks == 0

    manifest = IndexManifest.load(manifest_path)
    assert manifest.embedding_model == "model-v2-different"
