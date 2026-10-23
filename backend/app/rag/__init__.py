"""
backend/app/rag/__init__.py
===========================
RAG pipeline building blocks: normalization, scope classification,
evidence sufficiency evaluation, prompt construction, and citation validation.
"""
from backend.app.rag.citations import (
    build_citations_from_results,
    is_safe_and_approved_url,
    sanitize_markdown_links_in_answer,
    strip_inline_citations,
)
from backend.app.rag.normalize import normalize_query
from backend.app.rag.prompt_builder import (
    EVIDENCE_ONLY_SYSTEM_PROMPT,
    PromptContext,
    build_rag_messages,
)
from backend.app.rag.reference_resolver import resolve_query_context
from backend.app.rag.routing import QueryOutcomeCategory, map_outcome_to_chat_status
from backend.app.rag.scope_classifier import (
    OUT_OF_SCOPE_FALLBACK_TEXT,
    QueryScope,
    ScopeCategory,
    ScopeDecision,
    classify_scope,
    classify_scope_detailed,
)
from backend.app.rag.sufficiency import (
    INSUFFICIENT_EVIDENCE_FALLBACK_TEXT,
    SufficiencyDecision,
    SufficiencyOutcome,
    evaluate_evidence_sufficiency,
)

__all__ = [
    "normalize_query",
    "classify_scope",
    "classify_scope_detailed",
    "QueryScope",
    "ScopeCategory",
    "ScopeDecision",
    "OUT_OF_SCOPE_FALLBACK_TEXT",
    "resolve_query_context",
    "QueryOutcomeCategory",
    "map_outcome_to_chat_status",
    "evaluate_evidence_sufficiency",
    "SufficiencyDecision",
    "SufficiencyOutcome",
    "INSUFFICIENT_EVIDENCE_FALLBACK_TEXT",
    "build_rag_messages",
    "PromptContext",
    "EVIDENCE_ONLY_SYSTEM_PROMPT",
    "build_citations_from_results",
    "is_safe_and_approved_url",
    "sanitize_markdown_links_in_answer",
    "strip_inline_citations",
]

