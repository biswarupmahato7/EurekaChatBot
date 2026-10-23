"""
backend/app/services/chat_service.py
====================================
End-to-end RAG Chat orchestration service.
Follows Problem Statement §§9–11, Architecture §6, and Task Requirements:
- Normalizes incoming query.
- Contextual reference resolution (pronouns 'they', 'it', 'their' -> 'Eureka Solutions').
- Comprehensive scope classification with friendly domain-aware redirects for out-of-scope queries.
- Vector retrieval using contextualized query.
- Evidence sufficiency evaluation distinguishing known facts from unknown facts.
- Nuanced evidence-aware prompting (Case A, B, C, D) via Groq.
- Safe citation sanitization and inline citation stripping.
- Output post-processing mapping to public ChatStatus.
- Sanitized operational telemetry.
"""
from __future__ import annotations

import logging
import time
from typing import Any, Optional

from backend.app.config import AppSettings
from backend.app.llm.exceptions import (
    LLMBadRequestError,
    LLMConfigError,
    LLMError,
    LLMRateLimitError,
    LLMResponseMalformedError,
    LLMTimeoutError,
    LLMUnavailableError,
)
from backend.app.llm.groq_client import GroqClient
from backend.app.llm.openai_client import OpenAIClient
from backend.app.rag.citations import (
    build_citations_from_results,
    sanitize_contact_details,
    sanitize_markdown_links_in_answer,
    strip_inline_citations,
)
from backend.app.rag.conversation_router import route_conversation, ConversationIntent
from backend.app.rag.normalize import normalize_query
from backend.app.rag.prompt_builder import PromptContext, build_rag_messages
from backend.app.rag.reference_resolver import resolve_query_context
from backend.app.rag.routing import QueryOutcomeCategory, map_outcome_to_chat_status
from backend.app.rag.scope_classifier import (
    OUT_OF_SCOPE_FALLBACK_TEXT,
    ScopeCategory,
    classify_scope_detailed,
)
from backend.app.rag.sufficiency import (
    INSUFFICIENT_EVIDENCE_FALLBACK_TEXT,
    evaluate_evidence_sufficiency,
)
from backend.app.schemas.chat import ChatRequest, ChatResponse, ChatStatus, SourceItem
from backend.retrieval.models import SearchResult

logger = logging.getLogger(__name__)

SERVICE_UNAVAILABLE_FALLBACK_TEXT = (
    "Our service is temporarily unavailable. Please check the official Eureka Solutions "
    "website at https://eurekasolutions.in/Eureka2026/ or try again shortly."
)


class ChatService:
    """
    Coordinates query normalization, contextual reference resolution, scope classification,
    vector retrieval, evidence sufficiency checking, bounded prompt assembly, Groq completion,
    citation validation, and privacy-conscious operational telemetry.
    """

    def __init__(
        self,
        retriever: Any,  # SemanticRetriever or compatible duck-type / mock
        llm_client: Any,  # OpenAIClient, GroqClient, or compatible mock
        settings: AppSettings,
    ) -> None:
        self.retriever = retriever
        self.llm_client = llm_client
        self.settings = settings

    async def handle_chat_request(
        self,
        request: ChatRequest,
        request_id: str,
    ) -> tuple[ChatResponse, dict[str, Any]]:
        """
        Execute the full chat query lifecycle and return both the user-facing response
        and sanitized performance telemetry for logging.
        """
        start_time = time.monotonic()
        retrieval_latency = 0.0
        generation_latency = 0.0
        retrieved_count = 0
        validated_sources_count = 0
        status: ChatStatus = ChatStatus.ANSWERED
        error_category: Optional[str] = None

        try:
            # 1. Normalize Query
            normalized_query = normalize_query(request.message)

            # 2. Conversation Routing & Intent Policy
            router_decision = route_conversation(
                normalized_query,
                conversation_history=request.conversation_history,
            )

            if not router_decision.is_rag_required:
                status = router_decision.public_status
                response = ChatResponse(
                    request_id=request_id,
                    answer=router_decision.response_text,
                    status=status,
                    sources=[],
                    quick_replies=router_decision.quick_replies,
                )
                return response, self._compile_metrics(
                    start_time,
                    retrieval_latency,
                    generation_latency,
                    retrieved_count,
                    validated_sources_count,
                    status,
                    error_category,
                )

            # 3. Contextual Reference Resolution
            # Use clean query (profanities stripped for vector embedding)
            query_for_retrieval = router_decision.clean_query or normalized_query
            resolved_query = resolve_query_context(
                query_for_retrieval,
                request.conversation_history,
            )
            if resolved_query != normalized_query:
                logger.debug(
                    "Contextually resolved query from '%s' to '%s' (intent=%s, req=%s)",
                    normalized_query,
                    resolved_query,
                    router_decision.intent.value,
                    request_id,
                )

            # 4. Vector Retrieval
            t_retrieval = time.monotonic()
            try:
                if hasattr(self.retriever, "retrieve"):
                    res = self.retriever.retrieve(
                        query=resolved_query,
                        top_k=self.settings.retrieval_top_k,
                    )
                    search_results: list[SearchResult] = (
                        res.results if hasattr(res, "results") else res
                    )
                elif hasattr(self.retriever, "search"):
                    search_results = self.retriever.search(
                        query=resolved_query,
                        top_k=self.settings.retrieval_top_k,
                    )
                else:
                    raise RuntimeError("Configured retriever does not implement retrieve() or search().")
                retrieval_latency = time.monotonic() - t_retrieval
                retrieved_count = len(search_results)
            except Exception as exc:
                retrieval_latency = time.monotonic() - t_retrieval
                logger.error("Vector retrieval error for req %s: %s", request_id, type(exc).__name__)
                status = ChatStatus.TEMPORARILY_UNAVAILABLE
                error_category = "retrieval_failure"
                response = ChatResponse(
                    request_id=request_id,
                    answer=SERVICE_UNAVAILABLE_FALLBACK_TEXT,
                    status=status,
                    sources=[],
                )
                return response, self._compile_metrics(
                    start_time,
                    retrieval_latency,
                    generation_latency,
                    retrieved_count,
                    validated_sources_count,
                    status,
                    error_category,
                )

            # 5. Evidence Sufficiency Evaluation & Candidate Filtering
            if not search_results or len(search_results) == 0:
                status = ChatStatus.INSUFFICIENT_EVIDENCE
                response = ChatResponse(
                    request_id=request_id,
                    answer=INSUFFICIENT_EVIDENCE_FALLBACK_TEXT,
                    status=status,
                    sources=[],
                )
                return response, self._compile_metrics(
                    start_time,
                    retrieval_latency,
                    generation_latency,
                    retrieved_count,
                    validated_sources_count,
                    status,
                    error_category,
                )

            # Filter candidates with negligible text
            valid_candidates = [
                r for r in search_results
                if (getattr(r, "text", "") or getattr(r, "chunk_text", "")).strip()
                and len((getattr(r, "text", "") or getattr(r, "chunk_text", "")).strip()) > 10
            ]
            if not valid_candidates:
                status = ChatStatus.INSUFFICIENT_EVIDENCE
                response = ChatResponse(
                    request_id=request_id,
                    answer=INSUFFICIENT_EVIDENCE_FALLBACK_TEXT,
                    status=status,
                    sources=[],
                )
                return response, self._compile_metrics(
                    start_time,
                    retrieval_latency,
                    generation_latency,
                    retrieved_count,
                    validated_sources_count,
                    status,
                    error_category,
                )

            top_score = max(
                (r.score for r in valid_candidates if getattr(r, "score", None) is not None),
                default=0.0,
            )

            # If candidates have virtually zero similarity (< 0.20), avoid wasting an LLM call
            if top_score < 0.20:
                status = ChatStatus.INSUFFICIENT_EVIDENCE
                response = ChatResponse(
                    request_id=request_id,
                    answer=INSUFFICIENT_EVIDENCE_FALLBACK_TEXT,
                    status=status,
                    sources=[],
                )
                return response, self._compile_metrics(
                    start_time,
                    retrieval_latency,
                    generation_latency,
                    retrieved_count,
                    validated_sources_count,
                    status,
                    error_category,
                )

            # 6. Build Controlled Prompt
            prompt_context = PromptContext(
                question=normalized_query,
                chunks=valid_candidates,
                language=request.language,
                conversation_history=request.conversation_history,
            )
            messages = build_rag_messages(prompt_context)

            # 7. LLM Generation
            t_gen = time.monotonic()
            provider = self.settings.llm_provider.strip().lower()
            tokens = (
                self.settings.openai_max_output_tokens
                if provider == "openai"
                else self.settings.groq_max_output_tokens
            )
            try:
                raw_answer = await self.llm_client.agenerate(
                    messages=messages,
                    max_tokens=tokens,
                )
                generation_latency = time.monotonic() - t_gen
            except LLMConfigError as exc:
                generation_latency = time.monotonic() - t_gen
                logger.warning("LLM configuration unavailable (%s): %s", provider, exc)
                status = ChatStatus.TEMPORARILY_UNAVAILABLE
                error_category = "llm_config_error"
                response = ChatResponse(
                    request_id=request_id,
                    answer=SERVICE_UNAVAILABLE_FALLBACK_TEXT,
                    status=status,
                    sources=[],
                )
                return response, self._compile_metrics(
                    start_time,
                    retrieval_latency,
                    generation_latency,
                    retrieved_count,
                    validated_sources_count,
                    status,
                    error_category,
                )
            except (LLMTimeoutError, LLMRateLimitError, LLMUnavailableError) as exc:
                generation_latency = time.monotonic() - t_gen
                logger.warning("LLM provider transient issue (%s, %s): %s", provider, type(exc).__name__, exc)
                status = ChatStatus.TEMPORARILY_UNAVAILABLE
                error_category = type(exc).__name__
                response = ChatResponse(
                    request_id=request_id,
                    answer=SERVICE_UNAVAILABLE_FALLBACK_TEXT,
                    status=status,
                    sources=[],
                )
                return response, self._compile_metrics(
                    start_time,
                    retrieval_latency,
                    generation_latency,
                    retrieved_count,
                    validated_sources_count,
                    status,
                    error_category,
                )
            except (LLMBadRequestError, LLMResponseMalformedError, LLMError) as exc:
                generation_latency = time.monotonic() - t_gen
                logger.error("LLM provider error (%s, %s): %s", provider, type(exc).__name__, exc)
                status = ChatStatus.TEMPORARILY_UNAVAILABLE
                error_category = type(exc).__name__
                response = ChatResponse(
                    request_id=request_id,
                    answer=SERVICE_UNAVAILABLE_FALLBACK_TEXT,
                    status=status,
                    sources=[],
                )
                return response, self._compile_metrics(
                    start_time,
                    retrieval_latency,
                    generation_latency,
                    retrieved_count,
                    validated_sources_count,
                    status,
                    error_category,
                )

            # 8. Build and Validate Citations
            citations = build_citations_from_results(
                valid_candidates,
                max_citations=self.settings.max_citations,
                allowed_domains=self.settings.allowed_citation_domains,
            )

            # Sanitize any hallucinated markdown links in answer
            safe_answer = sanitize_markdown_links_in_answer(raw_answer, citations)
            safe_answer = strip_inline_citations(safe_answer)
            safe_answer = sanitize_contact_details(safe_answer)

            # 9. Determine Status & Distinguish Insufficient Evidence
            lower_answer = safe_answer.lower()
            insufficient_phrases = (
                "couldn't find",
                "could not find",
                "cannot find",
                "unable to find",
                "couldn't confirm",
                "could not confirm",
                "cannot confirm",
                "unable to confirm",
                "cannot verify",
                "could not verify",
                "couldn't verify",
                "unable to verify",
                "cannot provide",
                "unable to provide",
                "no mention of",
                "not mentioned in",
                "not stated in",
                "does not mention",
                "do not mention",
                "does not contain",
                "do not contain",
                "does not include",
                "do not include",
                "does not confirm",
                "do not confirm",
                "there is no",
                "there are no",
                "no historical",
                "not documented",
                "undocumented",
                "not a publicly traded",
                "not a publicly listed",
                "does not provide information",
                "do not provide information",
                "no information is provided",
                "not available in the",
                "recommend checking directly with eureka solutions",
                "recommend checking with the company directly",
                "recommend reaching out directly",
                "contacting the company directly",
                "contact the company directly",
            )



            if any(phrase in lower_answer for phrase in insufficient_phrases):
                status = ChatStatus.INSUFFICIENT_EVIDENCE
                # Retain citations only if the candidate chunk actually supported the partial verified fact
                # (e.g. Mumbai base from Privacy Policy chunk with score >= 0.40)
                sources = [
                    c for c in citations
                    if any(
                        chunk.source_url == c.url and (getattr(chunk, "score", 0.0) or 0.0) >= 0.40
                        for chunk in valid_candidates
                    )
                ]
                validated_sources_count = len(sources)
            else:
                status = ChatStatus.ANSWERED
                sources = citations
                validated_sources_count = len(sources)

            response = ChatResponse(
                request_id=request_id,
                answer=safe_answer,
                status=status,
                sources=sources,
                quick_replies=router_decision.quick_replies if router_decision.quick_replies else [],
            )
            return response, self._compile_metrics(
                start_time,
                retrieval_latency,
                generation_latency,
                retrieved_count,
                validated_sources_count,
                status,
                error_category,
            )

        except Exception as exc:
            logger.exception("Unexpected error in chat pipeline: %s", exc)
            status = ChatStatus.TEMPORARILY_UNAVAILABLE
            error_category = "unexpected_internal_error"
            response = ChatResponse(
                request_id=request_id,
                answer=SERVICE_UNAVAILABLE_FALLBACK_TEXT,
                status=status,
                sources=[],
            )
            return response, self._compile_metrics(
                start_time,
                retrieval_latency,
                generation_latency,
                retrieved_count,
                validated_sources_count,
                status,
                error_category,
            )

    @staticmethod
    def _compile_metrics(
        start_time: float,
        retrieval_latency: float,
        generation_latency: float,
        retrieved_count: int,
        validated_sources_count: int,
        status: ChatStatus,
        error_category: Optional[str],
    ) -> dict[str, Any]:
        """Compile sanitized operational telemetry."""
        total_latency = time.monotonic() - start_time
        return {
            "total_latency_seconds": round(total_latency, 4),
            "retrieval_latency_seconds": round(retrieval_latency, 4),
            "generation_latency_seconds": round(generation_latency, 4),
            "retrieved_chunks_count": retrieved_count,
            "validated_sources_count": validated_sources_count,
            "status": status.value,
            "error_category": error_category,
        }
