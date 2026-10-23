"""
backend/tests/test_retrieval.py
===============================
Tests for SemanticRetriever, query handling, deduplication, thresholds, and result contracts.
"""
from __future__ import annotations

import gc
import tempfile
from pathlib import Path

import pytest

from backend.embeddings.mock_embedder import MockEmbedder
from backend.indexing.index_builder import IndexBuilder
from backend.retrieval.retriever import SemanticRetriever
from backend.vectorstore.chroma_store import ChromaVectorStore

FIXTURES_DIR = Path(__file__).parent / "fixtures"
SAMPLE_CHUNKS_PATH = FIXTURES_DIR / "sample_chunks.json"


@pytest.fixture
def indexed_retriever():
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmpdir:
        tmp_path = Path(tmpdir)
        store = ChromaVectorStore(persist_directory=tmp_path / "vectorstore", collection_name="test_retrieval")
        embedder = MockEmbedder(dimension=384)
        builder = IndexBuilder(vector_store=store, embedder=embedder, manifest_path=tmp_path / "manifest.json")
        builder.build_index(chunks_file_path=SAMPLE_CHUNKS_PATH)

        retriever = SemanticRetriever(vector_store=store, embedder=embedder)
        yield retriever
        store.close()
        gc.collect()


def test_retrieval_returns_expected_fields(indexed_retriever: SemanticRetriever):
    resp = indexed_retriever.retrieve(query="custom enterprise ERP software", top_k=2)
    assert resp.total_results <= 2
    assert len(resp.results) > 0

    first = resp.results[0]
    assert first.chunk_id != ""
    assert first.page_id != ""
    assert first.text != ""
    assert first.source_url.startswith("https://")
    assert first.page_title != ""
    assert isinstance(first.heading_path, list)
    assert first.distance is not None
    assert first.score is not None


def test_empty_query_returns_empty_response(indexed_retriever: SemanticRetriever):
    resp = indexed_retriever.retrieve(query="   ", top_k=5)
    assert resp.total_results == 0
    assert resp.results == []


def test_top_k_bounds(indexed_retriever: SemanticRetriever):
    with pytest.raises(ValueError):
        indexed_retriever.retrieve(query="valid query", top_k=0)

    with pytest.raises(ValueError):
        indexed_retriever.retrieve(query="valid query", top_k=25)


def test_threshold_filtering(indexed_retriever: SemanticRetriever):
    # Without threshold, results are returned
    resp_all = indexed_retriever.retrieve(query="ERP solutions", top_k=4)
    assert len(resp_all.results) > 0

    # With impossible high threshold (e.g. 1.05), no results should pass
    resp_filtered = indexed_retriever.retrieve(query="ERP solutions", top_k=4, relevance_threshold=1.05)
    assert len(resp_filtered.results) == 0


def test_same_page_concentration_limiting(indexed_retriever: SemanticRetriever):
    # In sample_chunks.json, chunk_001 and chunk_002 share page_id "test_page_alpha"
    # Setting max_same_page_results=1 should return at most 1 chunk from page_alpha if alternatives exist
    resp = indexed_retriever.retrieve(
        query="ERP solutions and conversational AI",
        top_k=3,
        max_same_page_results=1,
    )
    pages = [r.page_id for r in resp.results]
    assert pages.count("test_page_alpha") <= 1


def test_empty_vector_store_behavior():
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmpdir:
        store = ChromaVectorStore(persist_directory=Path(tmpdir), collection_name="empty_col")
        try:
            embedder = MockEmbedder(dimension=384)
            retriever = SemanticRetriever(vector_store=store, embedder=embedder)

            resp = retriever.retrieve(query="any search term", top_k=5)
            assert resp.total_results == 0
            assert resp.results == []
        finally:
            store.close()
            gc.collect()
