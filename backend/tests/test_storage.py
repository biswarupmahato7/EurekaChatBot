"""
backend/tests/test_storage.py
=============================
Tests for ChromaVectorStore adapter.
Verifies persistence, idempotency, updates, querying, and empty collections.
"""
from __future__ import annotations

import gc
import tempfile
from pathlib import Path

import pytest

from backend.vectorstore.base import VectorRecord
from backend.vectorstore.chroma_store import ChromaVectorStore


@pytest.fixture
def temp_chroma_dir():
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmpdir:
        yield Path(tmpdir)
        gc.collect()


def test_collection_creation_and_count(temp_chroma_dir: Path):
    store = ChromaVectorStore(persist_directory=temp_chroma_dir, collection_name="test_collection")
    try:
        assert store.count() == 0
    finally:
        store.close()


def test_empty_collection_query(temp_chroma_dir: Path):
    store = ChromaVectorStore(persist_directory=temp_chroma_dir, collection_name="test_collection")
    try:
        results = store.query(query_embedding=[0.1] * 384, top_k=6)
        assert results == []
    finally:
        store.close()


def test_upsert_and_retrieve_record(temp_chroma_dir: Path):
    store = ChromaVectorStore(persist_directory=temp_chroma_dir, collection_name="test_collection")
    try:
        record = VectorRecord(
            id="chunk_1",
            embedding=[0.5] * 384,
            document="This is chunk 1 text content.",
            metadata={
                "page_id": "page_a",
                "source_url": "https://example.com/test",
                "page_title": "Test Title",
                "heading_path": ["Home", "Test"],
            },
        )
        store.upsert([record])
        assert store.count() == 1

        fetched = store.get(["chunk_1"])
        assert len(fetched) == 1
        assert fetched[0].id == "chunk_1"
        assert fetched[0].document == "This is chunk 1 text content."
        assert fetched[0].metadata["page_id"] == "page_a"
    finally:
        store.close()


def test_repeated_upsert_is_idempotent(temp_chroma_dir: Path):
    store = ChromaVectorStore(persist_directory=temp_chroma_dir, collection_name="test_collection")
    try:
        record = VectorRecord(
            id="chunk_same",
            embedding=[0.2] * 384,
            document="Static text content.",
            metadata={"token_count": 10},
        )
        store.upsert([record])
        assert store.count() == 1

        store.upsert([record])
        assert store.count() == 1
    finally:
        store.close()


def test_update_existing_record_preserves_count(temp_chroma_dir: Path):
    store = ChromaVectorStore(persist_directory=temp_chroma_dir, collection_name="test_collection")
    try:
        record_v1 = VectorRecord(
            id="chunk_update",
            embedding=[0.1] * 384,
            document="Initial text content.",
            metadata={"version": 1},
        )
        store.upsert([record_v1])
        assert store.count() == 1

        record_v2 = VectorRecord(
            id="chunk_update",
            embedding=[0.3] * 384,
            document="Updated text content.",
            metadata={"version": 2},
        )
        store.upsert([record_v2])
        assert store.count() == 1

        fetched = store.get(["chunk_update"])[0]
        assert fetched.document == "Updated text content."
        assert fetched.metadata["version"] == 2
    finally:
        store.close()


def test_persistence_survives_client_restart(temp_chroma_dir: Path):
    # Process 1 creates and writes
    store1 = ChromaVectorStore(persist_directory=temp_chroma_dir, collection_name="persist_col")
    store1.upsert([
        VectorRecord(id="c1", embedding=[0.1] * 384, document="Doc 1", metadata={"tag": "alpha"}),
        VectorRecord(id="c2", embedding=[0.2] * 384, document="Doc 2", metadata={"tag": "beta"}),
    ])
    assert store1.count() == 2
    store1.close()

    # Process 2 reopens the same persist directory
    store2 = ChromaVectorStore(persist_directory=temp_chroma_dir, collection_name="persist_col")
    try:
        assert store2.count() == 2
        fetched = store2.get(["c1", "c2"])
        ids = {r.id for r in fetched}
        assert ids == {"c1", "c2"}
    finally:
        store2.close()


def test_query_ranking_and_scores(temp_chroma_dir: Path):
    store = ChromaVectorStore(persist_directory=temp_chroma_dir, collection_name="query_col")
    try:
        vec_query = [1.0] + [0.0] * 383
        vec_match = [1.0] + [0.0] * 383
        vec_other = [0.0, 1.0] + [0.0] * 382

        store.upsert([
            VectorRecord(id="best_match", embedding=vec_match, document="Match doc", metadata={"page_id": "p1"}),
            VectorRecord(id="other_doc", embedding=vec_other, document="Other doc", metadata={"page_id": "p2"}),
        ])

        results = store.query(query_embedding=vec_query, top_k=2)
        assert len(results) == 2
        assert results[0].id == "best_match"
        assert results[0].score is not None
        assert results[0].score > results[1].score
    finally:
        store.close()


def test_reset_clears_collection(temp_chroma_dir: Path):
    store = ChromaVectorStore(persist_directory=temp_chroma_dir, collection_name="reset_col")
    try:
        store.upsert([VectorRecord(id="c1", embedding=[0.1] * 384, document="Text", metadata={})])
        assert store.count() == 1

        store.reset()
        assert store.count() == 0
    finally:
        store.close()
