"""
backend/tests/test_phase_boundaries.py
======================================
Architectural boundary tests for Phase B.

Verifies:
1. No Groq, OpenAI, or LLM generation libraries are imported in backend modules.
2. No LLM answer-generation or prompt-construction logic is present.
3. ChromaDB is the sole vector store implementation (no pgvector).
4. No FastAPI chat routes or chat endpoints are defined in Phase B.
5. Retrieval output contract returns raw chunks with scores and metadata only.
"""
from __future__ import annotations

import ast
import inspect
from pathlib import Path

import pytest

import backend.embeddings
import backend.indexing
import backend.retrieval
import backend.vectorstore
from backend.retrieval.models import RetrievalResponse, SearchResult
from backend.retrieval.retriever import SemanticRetriever
from backend.vectorstore.base import BaseVectorStore
from backend.vectorstore.chroma_store import ChromaVectorStore

BACKEND_DIR = Path(__file__).resolve().parent.parent


def test_no_forbidden_llm_imports():
    """
    Verify architectural boundaries:
    - Phase B retrieval/embedding/indexing/storage modules must have NO LLM imports.
    - In Phase C backend/app, only 'openai' (and legacy 'groq') are permitted under backend/app/llm.
    - No Anthropic, Cohere, LangChain, LlamaIndex, or SQL/pgvector dependencies anywhere.
    """
    phase_b_dirs = [
        BACKEND_DIR / "embeddings",
        BACKEND_DIR / "indexing",
        BACKEND_DIR / "retrieval",
        BACKEND_DIR / "vectorstore",
    ]

    llm_libraries = {"openai", "groq"}

    forbidden_everywhere = {
        "anthropic",
        "cohere",
        "langchain",
        "llama_index",
        "psycopg2",
        "asyncpg",
        "pgvector",
    }

    violations: list[str] = []

    # 1. Phase B modules must have zero LLM imports
    for p_dir in phase_b_dirs:
        for py_file in p_dir.rglob("*.py"):
            try:
                tree = ast.parse(py_file.read_text(encoding="utf-8"))
            except Exception as exc:
                violations.append(f"Could not parse {py_file}: {exc}")
                continue

            for node in ast.walk(tree):
                if isinstance(node, ast.Import):
                    for alias in node.names:
                        root_pkg = alias.name.split(".")[0]
                        if root_pkg in forbidden_everywhere or root_pkg in llm_libraries:
                            violations.append(f"Phase B {py_file.name} imports forbidden LLM module: {alias.name}")
                elif isinstance(node, ast.ImportFrom):
                    if node.module:
                        root_pkg = node.module.split(".")[0]
                        if root_pkg in forbidden_everywhere or root_pkg in llm_libraries:
                            violations.append(f"Phase B {py_file.name} imports from forbidden LLM module: {node.module}")

    # 2. Entire backend must never import forbidden alternative frameworks,
    # and direct LLM libraries (openai, groq) are isolated strictly to backend/app/llm
    for py_file in BACKEND_DIR.rglob("*.py"):
        if py_file.name in ("test_phase_boundaries.py", "test_groq_client.py", "test_openai_client.py"):
            continue
        try:
            tree = ast.parse(py_file.read_text(encoding="utf-8"))
        except Exception:
            continue
        is_llm_module = "backend/app/llm" in py_file.as_posix()
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    root_pkg = alias.name.split(".")[0]
                    if root_pkg in forbidden_everywhere:
                        violations.append(f"{py_file.name} imports forbidden module: {alias.name}")
                    elif root_pkg in llm_libraries and not is_llm_module:
                        violations.append(f"{py_file.name} imports direct LLM library outside backend/app/llm: {alias.name}")
            elif isinstance(node, ast.ImportFrom):
                if node.module:
                    root_pkg = node.module.split(".")[0]
                    if root_pkg in forbidden_everywhere:
                        violations.append(f"{py_file.name} imports from forbidden module: {node.module}")
                    elif root_pkg in llm_libraries and not is_llm_module:
                        violations.append(f"{py_file.name} imports direct LLM library outside backend/app/llm: {node.module}")

    assert not violations, f"Forbidden architectural imports detected:\n" + "\n".join(violations)


def test_chroma_is_sole_vector_store():
    """Verify BaseVectorStore is implemented only by ChromaVectorStore (no pgvector)."""
    subclasses = BaseVectorStore.__subclasses__()
    class_names = [cls.__name__ for cls in subclasses]
    assert "ChromaVectorStore" in class_names
    for name in class_names:
        assert "pgvector" not in name.lower()
        assert "postgres" not in name.lower()


def test_retriever_returns_chunks_only_no_generation():
    """Verify SemanticRetriever returns structured chunks and metadata without answer generation."""
    sig = inspect.signature(SemanticRetriever.retrieve)
    return_annotation = sig.return_annotation
    assert return_annotation == RetrievalResponse or return_annotation == "RetrievalResponse"

    fields = RetrievalResponse.model_fields
    assert "results" in fields
    assert "query" in fields
    assert "top_k" in fields
    # Ensure no answer/generation fields exist in retrieval layer
    assert "answer" not in fields
    assert "generated_text" not in fields
    assert "llm_response" not in fields


def test_no_chat_api_routes():
    """Verify that Phase B retrieval and indexing packages do not introduce FastAPI routes."""
    phase_b_dirs = [
        BACKEND_DIR / "embeddings",
        BACKEND_DIR / "indexing",
        BACKEND_DIR / "retrieval",
        BACKEND_DIR / "vectorstore",
    ]
    for p_dir in phase_b_dirs:
        for py_file in p_dir.rglob("*.py"):
            content = py_file.read_text(encoding="utf-8")
            assert "@app.post" not in content
            assert "@router.post" not in content
