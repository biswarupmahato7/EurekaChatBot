"""
backend/app/rag/sufficiency.py
==============================
Evidence sufficiency evaluation module for Eureka RAG Chatbot.

Evaluates whether retrieved chunks contain adequate, relevant evidence to ground
an answer before making an LLM generation call. Follows Problem Statement §11.2.
"""
from __future__ import annotations

import enum
from typing import Iterator, Optional, Union

from backend.retrieval.models import SearchResult

# Standardized fallback specified in Problem Statement §11.2 without repetitive homepage URL
INSUFFICIENT_EVIDENCE_FALLBACK_TEXT = (
    "I couldn't find enough information about that in the available Eureka Solutions website content. "
    "I recommend checking directly with Eureka Solutions so you get an accurate answer."
)
INSUFFICIENT_EVIDENCE_FALLBACK = INSUFFICIENT_EVIDENCE_FALLBACK_TEXT

TEMPORARILY_UNAVAILABLE_FALLBACK = (
    "The Ask Eureka AI assistant is temporarily unavailable. "
    "Please try again in a few moments or visit https://eurekasolutions.in/Eureka2026/."
)


class SufficiencyOutcome(str, enum.Enum):
    SUFFICIENT = "sufficient"
    INSUFFICIENT = "insufficient"
    TEMPORARILY_UNAVAILABLE = "temporarily_unavailable"


class SufficiencyDecision:
    """Rich result object for evidence sufficiency decisions."""

    def __init__(
        self,
        is_sufficient: bool,
        outcome: SufficiencyOutcome,
        fallback_text: str = INSUFFICIENT_EVIDENCE_FALLBACK_TEXT,
        reason: str = "",
    ) -> None:
        self.is_sufficient = is_sufficient
        self.outcome = outcome
        self.fallback_text = fallback_text
        self.reason = reason

    def __bool__(self) -> bool:
        return self.is_sufficient

    def __iter__(self) -> Iterator[Union[bool, str]]:
        """Support tuple unpacking: is_sufficient, fallback = evaluate_evidence_sufficiency(...)"""
        yield self.is_sufficient
        yield self.fallback_text


def evaluate_evidence_sufficiency(
    candidates_or_query: Union[str, list[SearchResult]] = None,
    candidates: Optional[list[SearchResult]] = None,
    min_score: float = 0.45,
    min_results_count: int = 1,
    min_score_threshold: Optional[float] = None,
    query: Optional[str] = None,
) -> SufficiencyDecision:
    """
    Determine whether retrieved search results provide adequate grounded evidence.
    Flexible signature accepts both:
        evaluate_evidence_sufficiency(results, min_score_threshold=...)
    and:
        evaluate_evidence_sufficiency(query=..., candidates=..., min_score=...)
    """
    threshold = min_score_threshold if min_score_threshold is not None else min_score

    # Resolve results list
    if isinstance(candidates_or_query, list):
        results = candidates_or_query
    elif candidates is not None:
        results = candidates
    else:
        results = []

    if not results or len(results) < min_results_count:
        return SufficiencyDecision(
            is_sufficient=False,
            outcome=SufficiencyOutcome.INSUFFICIENT,
            fallback_text=INSUFFICIENT_EVIDENCE_FALLBACK_TEXT,
            reason="No search results retrieved.",
        )

    # Filter out empty or trivial text
    valid_chunks = [
        r for r in results
        if (getattr(r, "text", "") or getattr(r, "chunk_text", "")).strip()
        and len((getattr(r, "text", "") or getattr(r, "chunk_text", "")).strip()) > 10
    ]
    if not valid_chunks:
        return SufficiencyDecision(
            is_sufficient=False,
            outcome=SufficiencyOutcome.INSUFFICIENT,
            fallback_text=INSUFFICIENT_EVIDENCE_FALLBACK_TEXT,
            reason="Retrieved chunks have negligible or empty content.",
        )

    # Check top similarity score
    scores = [r.score for r in valid_chunks if getattr(r, "score", None) is not None]
    if scores:
        best_score = max(scores)
        if best_score < threshold:
            return SufficiencyDecision(
                is_sufficient=False,
                outcome=SufficiencyOutcome.INSUFFICIENT,
                fallback_text=INSUFFICIENT_EVIDENCE_FALLBACK_TEXT,
                reason=f"Top candidate score {best_score:.3f} is below threshold {threshold:.3f}.",
            )

    return SufficiencyDecision(
        is_sufficient=True,
        outcome=SufficiencyOutcome.SUFFICIENT,
        fallback_text="",
        reason="Evidence is sufficient for grounded generation.",
    )
