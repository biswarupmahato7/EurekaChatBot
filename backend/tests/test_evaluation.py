"""
backend/tests/test_evaluation.py
================================
Tests for RetrievalEvaluator, metric calculations, and golden dataset integrity.
"""
from __future__ import annotations

import gc
import json
import tempfile
from pathlib import Path

import pytest

from backend.embeddings.mock_embedder import MockEmbedder
from backend.evaluation.evaluate_retrieval import RetrievalEvaluator
from backend.indexing.index_builder import IndexBuilder
from backend.retrieval.retriever import SemanticRetriever
from backend.vectorstore.chroma_store import ChromaVectorStore

FIXTURES_DIR = Path(__file__).parent / "fixtures"
SAMPLE_CHUNKS_PATH = FIXTURES_DIR / "sample_chunks.json"


def test_golden_dataset_structure_and_validity():
    dataset_file = Path(__file__).resolve().parent.parent / "evaluation" / "golden_dataset.json"
    assert dataset_file.exists(), "golden_dataset.json must exist in backend/evaluation"

    with open(dataset_file, "r", encoding="utf-8") as f:
        data = json.load(f)

    assert "dataset_name" in data
    assert "queries" in data
    assert len(data["queries"]) >= 10, "Golden evaluation dataset should contain at least 10 queries"

    seen_ids = set()
    has_out_of_corpus = False
    has_typo = False

    for q in data["queries"]:
        assert "eval_id" in q
        assert q["eval_id"] not in seen_ids, f"Duplicate eval_id: {q['eval_id']}"
        seen_ids.add(q["eval_id"])
        assert "question" in q and len(q["question"]) > 0
        assert "category" in q

        if q["category"] == "out_of_corpus":
            has_out_of_corpus = True
            assert q["expected_page_ids"] == [], "out_of_corpus queries should have empty expected_page_ids"
        else:
            assert len(q["expected_page_ids"]) > 0, f"In-domain query {q['eval_id']} missing expected_page_ids"

        if q["category"] == "typo_variation":
            has_typo = True

    assert has_out_of_corpus, "Golden dataset must include an out-of-corpus query"
    assert has_typo, "Golden dataset must include a realistic typo query"


def test_evaluator_metrics_calculation():
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmpdir:
        tmp_path = Path(tmpdir)
        store = ChromaVectorStore(persist_directory=tmp_path / "vectorstore", collection_name="eval_test")
        try:
            embedder = MockEmbedder(dimension=384)
            builder = IndexBuilder(vector_store=store, embedder=embedder, manifest_path=tmp_path / "manifest.json")
            builder.build_index(chunks_file_path=SAMPLE_CHUNKS_PATH)

            retriever = SemanticRetriever(vector_store=store, embedder=embedder)

            # Create small test golden dataset
            test_golden = {
                "dataset_name": "Test Golden Set",
                "dataset_type": "fixture",
                "queries": [
                    {
                        "eval_id": "t1",
                        "question": "custom enterprise ERP software",
                        "expected_page_ids": ["test_page_alpha"],
                        "category": "exact_phrase",
                    },
                    {
                        "eval_id": "t2",
                        "question": "Conversational bots answering questions",
                        "expected_page_ids": ["test_page_beta"],
                        "category": "conversational",
                    },
                    {
                        "eval_id": "t3",
                        "question": "Quantum cryogenic physics",
                        "expected_page_ids": [],
                        "category": "out_of_corpus",
                    },
                ],
            }
            test_golden_file = tmp_path / "test_golden.json"
            with open(test_golden_file, "w", encoding="utf-8") as f:
                json.dump(test_golden, f)

            evaluator = RetrievalEvaluator(
                retriever=retriever,
                golden_dataset_path=test_golden_file,
            )

            report = evaluator.evaluate(top_k=4)
            assert report.total_queries == 3
            assert report.evaluable_queries == 2
            assert report.out_of_corpus_queries == 1
            assert 0.0 <= report.hit_rate_at_k <= 1.0
            assert 0.0 <= report.mrr <= 1.0
            assert len(report.results) == 3
        finally:
            store.close()
            gc.collect()
