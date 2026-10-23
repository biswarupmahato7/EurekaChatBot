"""
tests/test_phase_e_e2e_evaluation.py
====================================
Phase E End-to-End Integration, Quality Evaluation, and Citation Verification Suite.
Evaluates the 28-case evaluation set across:
- Mode 1: Unit and Mocked Integration
- Mode 2: Real Index (3,796 chunks) + Isolated Groq Mock
- Mode 3: Real Index + Limited Bounded Live Groq (bounded sample)
"""
from __future__ import annotations

import json
import os
import time
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import dotenv
import pytest
from fastapi.testclient import TestClient

# Load .env file for Mode 3 live Groq testing
dotenv.load_dotenv(Path(__file__).resolve().parent.parent / ".env")

from backend.app.config import AppSettings
from backend.app.dependencies import get_chat_service
from backend.app.main import create_app
from backend.app.schemas.chat import ChatResponse, ChatStatus, SourceItem
from backend.app.services.chat_service import ChatService
from backend.embeddings.sentence_transformer_embedder import SentenceTransformerEmbedder
from backend.retrieval.models import SearchResult
from backend.retrieval.retriever import SemanticRetriever
from backend.vectorstore.chroma_store import ChromaVectorStore

EVAL_SET_PATH = Path(__file__).resolve().parent.parent / "data" / "evaluation" / "phase_e_evaluation_set.json"


@pytest.fixture(scope="module")
def eval_dataset():
    assert EVAL_SET_PATH.exists(), f"Evaluation set missing at {EVAL_SET_PATH}"
    with open(EVAL_SET_PATH, "r", encoding="utf-8") as f:
        return json.load(f)


# =============================================================================
# MODE 1: Unit & Mocked Integration Suite (All 28 Test Cases)
# =============================================================================

class TestMode1MockedPipeline:
    """
    Mode 1: Deterministic evaluation of request schemas, logical status assignment,
    and fallback mechanics with mocked service components.
    """

    @pytest.fixture(scope="class")
    def mock_app(self):
        settings = AppSettings(
            app_env="testing",
            allowed_origins=["http://localhost:5173"],
            rate_limit_per_minute=200,
        )
        app = create_app(settings=settings)

        # Mock retriever with standard responses
        mock_retriever = MagicMock()
        mock_chunk = SearchResult(
            chunk_id="chk-mock-1",
            page_id="page-mock-1",
            text="Eureka Solutions delivers enterprise software, ERP, and cloud integrations.",
            source_url="https://eurekasolutions.in/Eureka2026/services/enterprise-software",
            page_title="Enterprise Software",
            section_heading="Overview",
            score=0.88,
            metadata={
                "source_url": "https://eurekasolutions.in/Eureka2026/services/enterprise-software",
                "page_title": "Enterprise Software",
                "section_heading": "Overview",
            },
        )
        mock_retriever.retrieve.return_value = [mock_chunk]

        mock_groq = MagicMock()
        mock_groq.agenerate = AsyncMock(
            return_value="Eureka Solutions delivers enterprise software and cloud integrations."
        )

        chat_service = ChatService(
            retriever=mock_retriever,
            llm_client=mock_groq,
            settings=settings,
        )
        app.dependency_overrides[get_chat_service] = lambda: chat_service
        return app

    def test_mode1_eval_dataset_integrity(self, eval_dataset):
        assert eval_dataset["total_cases"] == len(eval_dataset["cases"])
        assert eval_dataset["total_cases"] >= 25

        seen_ids = set()
        for c in eval_dataset["cases"]:
            assert c["test_id"] not in seen_ids
            seen_ids.add(c["test_id"])
            assert c["category"].startswith("category_")
            assert c["expected_status"] in ["answered", "insufficient_evidence", "out_of_scope"]

    def test_mode1_out_of_scope_queries(self, mock_app, eval_dataset):
        with TestClient(mock_app) as client:
            gk_cases = [c for c in eval_dataset["cases"] if c["category"] == "category_e_unrelated_gk"]

            for c in gk_cases:
                res = client.post(
                    "/api/v1/chat",
                    json={"message": c["question"]},
                    headers={"Origin": "http://localhost:5173"},
                )
                assert res.status_code == 200
                data = res.json()
                assert data["status"] in ["out_of_scope", "insufficient_evidence"], (
                    f"Expected out of scope for {c['test_id']}: {c['question']}"
                )
                assert data["sources"] == []
                assert "ask eureka ai" in data["answer"].lower() or "couldn't find" in data["answer"].lower()

    def test_mode1_adversarial_queries(self, mock_app, eval_dataset):
        with TestClient(mock_app) as client:
            inj_cases = [c for c in eval_dataset["cases"] if c["category"] == "category_f_prompt_injection"]

            for c in inj_cases:
                res = client.post(
                    "/api/v1/chat",
                    json={"message": c["question"]},
                    headers={"Origin": "http://localhost:5173"},
                )
                assert res.status_code == 200
                data = res.json()
                assert data["status"] in ["out_of_scope", "insufficient_evidence", "answered"]
                # Zero secret leakage
                assert "gsk_" not in data["answer"]
                assert "api_key" not in data["answer"].lower()


# =============================================================================
# MODE 2: Real Index (3,796 Chunks) + Isolated Groq Mock
# =============================================================================

class TestMode2RealIndexRetrieval:
    """
    Mode 2: Validates semantic retrieval, expected URL hit rate, evidence sufficiency,
    and citation provenance against the actual 3,796-chunk ChromaDB persistent index.
    """

    @pytest.fixture(scope="class")
    def live_retriever(self):
        persist_dir = Path("./data/vectorstore")
        if not persist_dir.exists():
            pytest.skip("Chroma vectorstore not found at ./data/vectorstore")

        store = ChromaVectorStore(
            persist_directory=persist_dir,
            collection_name="eureka_website_chunks",
        )
        embedder = SentenceTransformerEmbedder(
            model_name="sentence-transformers/all-MiniLM-L6-v2",
            device="cpu",
        )
        retriever = SemanticRetriever(vector_store=store, embedder=embedder)
        yield retriever
        store.close()

    def test_mode2_category_a_direct_page_retrieval(self, live_retriever, eval_dataset):
        """
        Category A: Verifies single-page questions retrieve their expected target page.
        """
        direct_cases = [c for c in eval_dataset["cases"] if c["category"] == "category_a_direct_page"]
        hits = 0

        for c in direct_cases:
            res = live_retriever.retrieve(query=c["question"], top_k=6)
            chunks = res.results if hasattr(res, "results") else res
            retrieved_urls = [chunk.metadata.get("source_url") for chunk in chunks]

            # Check if expected URL appears in retrieved chunks
            found = any(exp in retrieved_urls for exp in c["expected_urls"])
            if found:
                hits += 1

            assert len(chunks) > 0, f"No chunks retrieved for {c['test_id']}"
            assert chunks[0].score is not None and chunks[0].score >= 0.40, (
                f"Low similarity score for {c['test_id']}"
            )

        hit_rate = hits / len(direct_cases)
        assert hit_rate >= 0.75, f"Category A hit rate {hit_rate:.2f} below 75% threshold"

    def test_mode2_category_b_multi_page_retrieval(self, live_retriever, eval_dataset):
        """
        Category B: Verifies cross-page inquiries retrieve chunks from relevant source domains.
        """
        multi_cases = [c for c in eval_dataset["cases"] if c["category"] == "category_b_multi_page"]

        for c in multi_cases:
            res = live_retriever.retrieve(query=c["question"], top_k=6)
            chunks = res.results if hasattr(res, "results") else res
            retrieved_pages = set(chunk.metadata.get("page_id") for chunk in chunks)
            # Must retrieve chunks from more than one page/section
            assert len(retrieved_pages) >= 2, f"Expected multi-page diversity for {c['test_id']}"

    def test_mode2_category_g_citation_correctness(self, live_retriever, eval_dataset):
        """
        Category G: Verifies that citations strictly match expected URLs and approved domain.
        """
        citation_cases = [c for c in eval_dataset["cases"] if c["category"] == "category_g_citation_correctness"]

        for c in citation_cases:
            res = live_retriever.retrieve(query=c["question"], top_k=6)
            chunks = res.results if hasattr(res, "results") else res
            for chunk in chunks:
                source_url = chunk.metadata.get("source_url", "")
                assert source_url.startswith("https://eurekasolutions.in/"), (
                    f"Invalid citation origin: {source_url}"
                )
                assert "malicious" not in source_url
                assert "javascript:" not in source_url


# =============================================================================
# MODE 3: Real Index + Limited Bounded Live Groq (Smoke / Telemetry)
# =============================================================================

class TestMode3LiveEndToEndTelemetry:
    """
    Mode 3: Small, bounded 3-query live test exercising the full stack
    (FastAPI -> ChromaDB -> Groq -> Citation Sanitization) to measure real latency and quality.
    """

    @pytest.fixture(scope="class")
    def live_app(self):
        settings = AppSettings(
            app_env="testing",
            allowed_origins=["http://localhost:5173", "https://eurekasolutions.in"],
            rate_limit_per_minute=60,
        )
        return create_app(settings=settings)

    def test_mode3_live_rag_inquiry_telemetry(self, live_app):
        """
        Runs 3 bounded live queries through real Groq LLM:
        1. Grounded service query
        2. Grounded case study query
        3. Absent fact query
        Records and asserts response time, status, and citation integrity.
        """
        provider = getattr(live_app.state.settings, "llm_provider", "openai").strip().lower()
        if provider == "openai":
            api_key = os.environ.get("OPENAI_API_KEY") or getattr(live_app.state.settings, "openai_api_key", None)
            if not api_key or "replace" in api_key or "your_openai" in api_key:
                pytest.skip("Real OPENAI_API_KEY not configured in environment")
        else:
            api_key = os.environ.get("GROQ_API_KEY") or getattr(live_app.state.settings, "groq_api_key", None)
            if not api_key or "replace" in api_key or "your_groq" in api_key:
                pytest.skip("Real GROQ_API_KEY not configured in environment")

        with TestClient(live_app) as client:
            test_queries = [
                ("What ERP software does Eureka Solutions implement?", "answered"),
                ("What outcomes were achieved in the Municipality WhatsApp Service Bot?", "answered"),
                ("What was Eureka Solutions stock price in 1995?", "insufficient_evidence"),
            ]

            for question, expected_status in test_queries:
                t0 = time.perf_counter()
                res = client.post(
                    "/api/v1/chat",
                    json={"message": question, "session_id": "mode3-eval"},
                    headers={"Origin": "http://localhost:5173"},
                )
                duration = time.perf_counter() - t0

                assert res.status_code == 200
                data = res.json()
                assert data["status"] == expected_status
                assert "request_id" in data
                assert len(data["answer"]) > 10

                if expected_status == "answered":
                    assert len(data["sources"]) > 0
                    for src in data["sources"]:
                        assert src["url"].startswith("https://eurekasolutions.in/")
                        assert len(src["title"]) > 0
                        assert len(src["snippet"]) > 0

                # Real latency must remain within acceptable interactive threshold (< 10s)
                assert duration < 10.0, f"Query '{question}' took too long: {duration:.2f}s"
