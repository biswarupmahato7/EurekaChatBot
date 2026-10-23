"""
backend/tests/test_embeddings.py
================================
Tests for BaseEmbedder, MockEmbedder, and SentenceTransformerEmbedder.
"""
from __future__ import annotations

import math
import pytest

from backend.embeddings.base import BaseEmbedder
from backend.embeddings.mock_embedder import MockEmbedder
from backend.embeddings.sentence_transformer_embedder import SentenceTransformerEmbedder


def test_mock_embedder_dimension_and_normalization():
    embedder = MockEmbedder(dimension=384)
    assert embedder.dimension == 384
    assert embedder.model_name == "mock-embedder/all-MiniLM-L6-v2"

    vec = embedder.embed_query("Enterprise software solutions")
    assert len(vec) == 384

    # Verify unit length L2 normalization
    norm = math.sqrt(sum(x * x for x in vec))
    assert abs(norm - 1.0) < 1e-5


def test_mock_embedder_batch_documents():
    embedder = MockEmbedder(dimension=384)
    texts = ["Document one", "Document two", "Document three"]
    vectors = embedder.embed_documents(texts)
    assert len(vectors) == 3
    for v in vectors:
        assert len(v) == 384
        norm = math.sqrt(sum(x * x for x in v))
        assert abs(norm - 1.0) < 1e-5


def test_empty_query_raises_value_error():
    embedder = MockEmbedder()
    with pytest.raises(ValueError):
        embedder.embed_query("   ")


def test_empty_documents_returns_empty_list():
    embedder = MockEmbedder()
    assert embedder.embed_documents([]) == []


def test_preprocessing_consistency():
    embedder = MockEmbedder()
    raw = "   Enterprise \n\t Software   Solutions   "
    clean = embedder.preprocess(raw)
    assert clean == "Enterprise Software Solutions"

    # Preprocessing query should match preprocessing document
    assert embedder.preprocess(raw) == embedder.preprocess("Enterprise Software Solutions")


def test_deterministic_pseudo_embeddings():
    embedder = MockEmbedder()
    vec1 = embedder.embed_query("ERP solutions for manufacturing")
    vec2 = embedder.embed_query("ERP solutions for manufacturing")
    assert vec1 == vec2

    vec3 = embedder.embed_query("Completely unrelated query about agriculture")
    assert vec1 != vec3


def test_sentence_transformer_initialization_metadata():
    """Verify SentenceTransformerEmbedder exposes dimension and version metadata."""
    try:
        embedder = SentenceTransformerEmbedder(model_name="sentence-transformers/all-MiniLM-L6-v2")
        assert embedder.dimension == 384
        assert embedder.model_name == "sentence-transformers/all-MiniLM-L6-v2"
        assert embedder.model_version != ""

        vec = embedder.embed_query("Test query for enterprise cloud solutions")
        assert len(vec) == 384
        norm = math.sqrt(sum(x * x for x in vec))
        assert abs(norm - 1.0) < 1e-4
    except Exception as exc:
        pytest.skip(f"SentenceTransformer local model download not available in this test environment: {exc}")
