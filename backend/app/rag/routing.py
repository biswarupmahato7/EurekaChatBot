"""
backend/app/rag/routing.py
==========================
Explicit Query Outcome Categories for Eureka RAG Chatbot.
Follows requirements for query routing and public status mapping.
"""
from __future__ import annotations

import enum

from backend.app.schemas.chat import ChatStatus


class ConversationIntent(str, enum.Enum):
    """
    Internal conversation routing categories for incoming visitor messages.
    Distinguishes genuine website queries, off-topic requests, profanity/insults,
    mixed intent, and contextual follow-ups.
    """

    WEBSITE_QUERY = "website_query"
    OFF_TOPIC = "off_topic"
    ABUSIVE_OR_INSULTING = "abusive_or_insulting"
    WEBSITE_QUERY_WITH_PROFANITY = "website_query_with_profanity"
    MIXED_OR_AMBIGUOUS = "mixed_or_ambiguous"
    FOLLOW_UP = "follow_up"
    MEANINGLESS_OR_GIBBERISH = "meaningless_or_gibberish"


class QueryOutcomeCategory(str, enum.Enum):
    """
    Internal typed outcome categories for query processing and answer generation.
    Cleanly separates internal evaluation and routing from the public API schema.
    """

    ANSWERABLE_IN_SCOPE = "answerable_in_scope"
    IN_SCOPE_INSUFFICIENT = "in_scope_insufficient"
    UNRELATED_OUT_OF_SCOPE = "unrelated_out_of_scope"
    AMBIGUOUS = "ambiguous"
    TEMPORARILY_UNAVAILABLE = "temporarily_unavailable"


def map_intent_to_outcome(intent: ConversationIntent) -> QueryOutcomeCategory:
    """Map internal ConversationIntent to QueryOutcomeCategory."""
    mapping = {
        ConversationIntent.WEBSITE_QUERY: QueryOutcomeCategory.ANSWERABLE_IN_SCOPE,
        ConversationIntent.OFF_TOPIC: QueryOutcomeCategory.UNRELATED_OUT_OF_SCOPE,
        ConversationIntent.ABUSIVE_OR_INSULTING: QueryOutcomeCategory.UNRELATED_OUT_OF_SCOPE,
        ConversationIntent.WEBSITE_QUERY_WITH_PROFANITY: QueryOutcomeCategory.ANSWERABLE_IN_SCOPE,
        ConversationIntent.MIXED_OR_AMBIGUOUS: QueryOutcomeCategory.AMBIGUOUS,
        ConversationIntent.FOLLOW_UP: QueryOutcomeCategory.ANSWERABLE_IN_SCOPE,
        ConversationIntent.MEANINGLESS_OR_GIBBERISH: QueryOutcomeCategory.UNRELATED_OUT_OF_SCOPE,
    }
    return mapping.get(intent, QueryOutcomeCategory.AMBIGUOUS)


def map_outcome_to_chat_status(outcome: QueryOutcomeCategory) -> ChatStatus:
    """Map internal typed query outcome to the public ChatStatus contract."""
    mapping = {
        QueryOutcomeCategory.ANSWERABLE_IN_SCOPE: ChatStatus.ANSWERED,
        QueryOutcomeCategory.IN_SCOPE_INSUFFICIENT: ChatStatus.INSUFFICIENT_EVIDENCE,
        QueryOutcomeCategory.UNRELATED_OUT_OF_SCOPE: ChatStatus.OUT_OF_SCOPE,
        QueryOutcomeCategory.AMBIGUOUS: ChatStatus.ANSWERED,
        QueryOutcomeCategory.TEMPORARILY_UNAVAILABLE: ChatStatus.TEMPORARILY_UNAVAILABLE,
    }
    return mapping.get(outcome, ChatStatus.TEMPORARILY_UNAVAILABLE)

