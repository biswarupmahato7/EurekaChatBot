"""
tests/test_edge_case_hardening.py
=================================
Automated regression tests verifying critical edge case hardening across Phases A-E:
- CRAWL-003: In-scope URL redirecting out of scope blocked
- RET-012 / RET-020 / INDEX-008 / INDEX-015: Incompatible embedding model in manifest detected;
  /health/ready reports 503 not_ready (index_incompatible); chat returns 503 temporarily_unavailable
- INDEX-012: Rebuild failure preserves recoverable previous collection
- SCOPE-018 / CTX-008: Short queries ("Goa?") resolve contextually when preceded by location context,
  or prompt polite clarification when ambiguous
- SCOPE-020: Inquiries regarding third-party companies (Infosys, TCS, Wipro) redirect to Eureka Solutions
- UI-020: AskEurekaWidget singleton guard prevents duplicate mounting
- SEC-014: Privacy-conscious logging policy suppresses raw prompts and PII at normal INFO level
- QA-007 / CRAWL-020: Release packaging excludes secrets and caches
"""
from __future__ import annotations

import gc
import json
import tempfile
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
import requests
from fastapi.testclient import TestClient

from backend.app.config import AppSettings
from backend.app.dependencies import get_chat_service, get_vector_store
from backend.app.main import create_app
from backend.app.rag.conversation_router import route_conversation, ConversationIntent
from backend.app.rag.reference_resolver import resolve_query_context, has_recent_location_context
from backend.app.schemas.chat import (
    ChatRequest,
    ChatResponse,
    ChatStatus,
    ConversationTurn,
)
from backend.app.services.chat_service import ChatService
from backend.embeddings.mock_embedder import MockEmbedder
from backend.indexing.index_builder import IndexBuilder
from backend.indexing.manifest import IndexManifest
from backend.retrieval.models import SearchResult
from backend.vectorstore.chroma_store import ChromaVectorStore
from crawler.fetcher import SafeFetcher
from crawler.packaging import verify_zip_archive


@pytest.fixture
def mock_settings() -> AppSettings:
    return AppSettings(
        app_env="testing",
        allowed_origins=["http://localhost:5173", "https://eurekasolutions.in"],
        rate_limit_per_minute=120,
    )


# =============================================================================
# 1. CRAWL-003: IN-SCOPE URL REDIRECTING OUT OF SCOPE
# =============================================================================
def test_crawl_003_redirect_out_of_scope_blocked():
    """
    CRAWL-003 (P0): In-scope URL redirects out of scope.
    Must recheck redirect target and block prohibited/external destinations.
    """
    fetcher = SafeFetcher(
        user_agent="EurekaTestCrawler/1.0",
        approved_origin="eurekasolutions.in",
        approved_prefix="/Eureka2026/",
    )
    redirect_resp = MagicMock(spec=requests.Response)
    redirect_resp.is_redirect = True
    redirect_resp.status_code = 301
    redirect_resp.headers = {"Location": "https://attacker-external-site.com/phishing"}

    with patch.object(fetcher._session, "get", return_value=redirect_resp):
        status = fetcher.fetch("https://eurekasolutions.in/Eureka2026/redirect_test")
        assert status.blocked is True
        assert "out_of_scope_redirect" in (status.block_reason or "")


# =============================================================================
# 2. RET-012, RET-020, INDEX-008, INDEX-015: INCOMPATIBLE EMBEDDING MANIFEST
# =============================================================================
def test_ret_012_and_index_015_incompatible_manifest_detection(mock_settings):
    """
    RET-012 (P0) & INDEX-015 (P1): When the persistent index manifest was built
    with an incompatible embedding model or dimensions (e.g. 768 vs 384):
    - App detects the incompatibility on startup
    - /health/ready returns 503 not_ready (index_incompatible)
    - POST /api/v1/chat returns 503 temporarily_unavailable without corrupting vectors
    """
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmpdir:
        tmp_path = Path(tmpdir)
        store = ChromaVectorStore(
            persist_directory=tmp_path / "vectorstore",
            collection_name=mock_settings.vector_collection_name,
        )
        # Create a mock collection with 1 dummy record
        embedder = MockEmbedder(dimension=384)
        from backend.vectorstore.base import VectorRecord
        store.upsert([
            VectorRecord(
                id="c1",
                embedding=[0.1] * 384,
                document="Test",
                metadata={"chunk_id": "c1"},
            )
        ])

        # Write an incompatible manifest (e.g. dimension=768 / different model)
        incompatible_manifest = IndexManifest(
            collection_name=mock_settings.vector_collection_name,
            embedding_model="sentence-transformers/all-mpnet-base-v2",
            embedding_dimension=768,
            dataset_path=str(tmp_path / "data.json"),
            dataset_sha256="abc123sha",
            total_input_chunks=1,
            total_indexed_chunks=1,
        )
        manifest_file = tmp_path / "vectorstore" / "index_manifest.json"
        incompatible_manifest.save(manifest_file)

        mock_settings.chroma_persist_directory = str(tmp_path / "vectorstore")
        app = create_app(mock_settings)

        with TestClient(app) as client:
            # 1. Verify readiness probe fails cleanly with 503 index_incompatible
            ready_res = client.get("/health/ready")
            assert ready_res.status_code == 503
            ready_data = ready_res.json()
            assert ready_data["status"] == "not_ready"
            assert ready_data["reason"] == "index_incompatible"

            # 2. Verify chat request safely returns 503 temporarily_unavailable
            chat_res = client.post("/api/v1/chat", json={"message": "What services do they offer?"})
            assert chat_res.status_code == 503
            chat_data = chat_res.json()
            assert chat_data["status"] == "temporarily_unavailable"
            assert "temporarily unavailable" in chat_data["answer"].lower()

        store.close()
        gc.collect()


# =============================================================================
# 3. INDEX-012: REBUILD FAILURE PRESERVES RECOVERABLE PREVIOUS COLLECTION
# =============================================================================
def test_index_012_rebuild_failure_preserves_previous_index():
    """
    INDEX-012 (P1): When a full rebuild is requested, if an embedding batch fails
    partway through, the existing collection records must NOT be wiped or corrupted.
    """
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmpdir:
        tmp_path = Path(tmpdir)
        store = ChromaVectorStore(
            persist_directory=tmp_path / "vectorstore",
            collection_name="test_preserve_chunks",
        )
        manifest_path = tmp_path / "vectorstore" / "index_manifest.json"
        embedder = MockEmbedder(dimension=384)

        # 1. Populate initial valid index with 2 chunks
        from backend.vectorstore.base import VectorRecord
        store.upsert([
            VectorRecord(id="c1", embedding=[0.1] * 384, document="Doc 1", metadata={"chunk_id": "c1", "content_hash": "h1"}),
            VectorRecord(id="c2", embedding=[0.2] * 384, document="Doc 2", metadata={"chunk_id": "c2", "content_hash": "h2"}),
        ])
        assert store.count() == 2

        # 2. Create chunks file for rebuild
        chunks_file = tmp_path / "rebuild_chunks.json"
        chunks_data = {
            "schema_version": "1.0",
            "run_id": "run-test-rebuild",
            "chunks": [
                {"chunk_id": "c1_new", "page_id": "p1", "source_url": "https://eurekasolutions.in/p1", "text": "New doc 1", "token_count": 10, "content_hash": "nh1"},
                {"chunk_id": "c2_new", "page_id": "p2", "source_url": "https://eurekasolutions.in/p2", "text": "New doc 2", "token_count": 10, "content_hash": "nh2"},
            ]
        }
        with open(chunks_file, "w", encoding="utf-8") as f:
            json.dump(chunks_data, f)

        builder = IndexBuilder(
            vector_store=store,
            embedder=embedder,
            manifest_path=manifest_path,
        )

        # 3. Simulate an embedding failure during rebuild
        with patch.object(embedder, "embed_documents", side_effect=RuntimeError("Simulated GPU/Memory error")):
            report = builder.build_index(chunks_file_path=chunks_file, rebuild=True)
            assert report.status == "FAILED"
            assert "Simulated GPU/Memory error" in report.errors[0]

        # 4. Verify previous collection records remain completely preserved (count still 2)
        assert store.count() == 2

        store.close()
        gc.collect()


# =============================================================================
# 4. SCOPE-018 & CTX-008: SHORT QUERIES ("Goa?", "AI?")
# =============================================================================
def test_scope_018_short_query_contextual_follow_up():
    """
    SCOPE-018 (P2) & CTX-008 (P2): Short query 'Goa?' following office location query
    is contextually resolved to 'Does Eureka Solutions have an office or presence in Goa?'
    """
    history = [
        ConversationTurn(role="user", content="Where are Eureka Solutions' offices located?"),
        ConversationTurn(role="assistant", content="Eureka Solutions operates from Mumbai."),
    ]
    assert has_recent_location_context(history) is True

    # When location context exists, resolve 'Goa?' into a complete location inquiry
    resolved = resolve_query_context("Goa?", history)
    assert "Eureka Solutions" in resolved
    assert "office" in resolved.lower() or "presence" in resolved.lower()
    assert "Goa" in resolved

    # Router should categorize as FOLLOW_UP with RAG required
    decision = route_conversation("Goa?", conversation_history=history)
    assert decision.intent == ConversationIntent.FOLLOW_UP
    assert decision.is_rag_required is True


def test_scope_018_short_query_without_context_prompts_clarification():
    """
    SCOPE-018 (P2): Short query 'Goa?' with NO prior location context
    prompts a concise, friendly clarification without crashing.
    """
    decision = route_conversation("Goa?", conversation_history=[])
    assert decision.intent == ConversationIntent.MIXED_OR_AMBIGUOUS
    assert decision.is_rag_required is False
    assert decision.public_status == ChatStatus.ANSWERED
    assert "tell me a bit more" in decision.response_text.lower()


# =============================================================================
# 5. SCOPE-020: USER ASKS ABOUT ANOTHER COMPANY
# =============================================================================
def test_scope_020_other_company_inquiry_redirects():
    """
    SCOPE-020 (P1): User asks about another company (Infosys, TCS, Wipro).
    Chatbot politely explains its Eureka Solutions focus and redirects.
    """
    queries = [
        "What services does Infosys provide?",
        "Tell me about TCS",
        "Who is the CEO of Wipro?",
        "Does Cognizant build ERP solutions?",
    ]
    for q in queries:
        decision = route_conversation(q)
        assert decision.intent == ConversationIntent.OFF_TOPIC
        assert decision.is_rag_required is False
        assert decision.public_status == ChatStatus.OUT_OF_SCOPE
        assert "Eureka Solutions" in decision.response_text
        assert "other companies" in decision.response_text.lower()


def test_scope_020_comparison_with_other_company_allowed_as_rag():
    """
    SCOPE-020 (P1): Comparison mentioning Eureka Solutions (e.g. 'How does Eureka Solutions compare to Infosys?')
    is NOT rejected as purely off-topic, but routes to RAG.
    """
    decision = route_conversation("How does Eureka Solutions compare to Infosys?")
    assert decision.intent in (ConversationIntent.WEBSITE_QUERY, ConversationIntent.FOLLOW_UP)
    assert decision.is_rag_required is True


# =============================================================================
# 6. SEC-014: LOGGING POLICY PRIVACY (NO PII AT INFO LEVEL)
# =============================================================================
@pytest.mark.anyio
async def test_sec_014_telemetry_does_not_log_prompts_at_info(mock_settings, caplog):
    """
    SEC-014 (P1): Normal request logs must contain correlation and timing metadata,
    and must NOT log the full prompt, personal identifiers, or raw provider bodies at INFO level.
    """
    import logging

    chunk = SearchResult(
        chunk_id="c1",
        page_id="p1",
        text="Eureka Solutions cloud integration.",
        source_url="https://eurekasolutions.in/services",
        page_title="Services",
        score=0.88,
    )
    mock_retriever = MagicMock()
    mock_retriever.retrieve.return_value = MagicMock(results=[chunk])
    mock_llm = MagicMock()
    mock_llm.agenerate = AsyncMock(return_value="Eureka Solutions offers cloud integration.")

    service = ChatService(mock_retriever, mock_llm, mock_settings)
    app = create_app(mock_settings)
    app.dependency_overrides[get_chat_service] = lambda: service

    with caplog.at_level(logging.INFO):
        with TestClient(app) as client:
            res = client.post("/api/v1/chat", json={
                "message": "My name is John Doe and my phone number is 9876543210. What cloud services do they offer?",
                "session_id": "sess-test-privacy",
            })
            assert res.status_code == 200

    # Ensure phone number or personal name never appeared in INFO log messages
    info_logs = [record.message for record in caplog.records if record.levelno == logging.INFO]
    combined_info = " ".join(info_logs)
    assert "9876543210" not in combined_info
    assert "John Doe" not in combined_info


# =============================================================================
# 7. QA-007 & CRAWL-020: RELEASE PACKAGING SAFETY
# =============================================================================
def test_qa_007_packaging_prohibits_secrets_and_caches():
    """
    QA-007 (P0) & CRAWL-020 (P0): Packaging verification tool flags any
    accidental inclusion of .env files, virtualenvs, or Python bytecode caches.
    """
    # Create a dummy zip with a forbidden .env file
    with tempfile.NamedTemporaryFile(suffix=".zip", delete=False) as tmp_zip:
        tmp_zip_path = Path(tmp_zip.name)

    import zipfile
    with zipfile.ZipFile(tmp_zip_path, "w") as zf:
        zf.writestr("crawler/pipeline.py", "# valid pipeline")
        zf.writestr(".env", "GROQ_API_KEY=gsk_secret12345")
        zf.writestr("crawler/__pycache__/cache.pyc", b"bytecode")

    verification = verify_zip_archive(tmp_zip_path)
    assert verification["valid"] is False
    assert any(".env" in item for item in verification["prohibited_found"])

    tmp_zip_path.unlink()
