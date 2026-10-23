"""
backend/app/schemas/chat.py
===========================
Data contracts for chat requests, responses, sources, and status enumerations.
Follows Problem Statement §9.2 and Architecture §6.2.
"""
from __future__ import annotations

import enum
from typing import Optional

from pydantic import BaseModel, Field, field_validator


class ChatStatus(str, enum.Enum):
    """Stable logical statuses for chatbot responses."""

    ANSWERED = "answered"
    INSUFFICIENT_EVIDENCE = "insufficient_evidence"
    OUT_OF_SCOPE = "out_of_scope"
    TEMPORARILY_UNAVAILABLE = "temporarily_unavailable"


class SourceItem(BaseModel):
    """A grounded citation reference pointing to an approved website page."""

    title: str = Field(description="Title of the source webpage or section")
    url: str = Field(description="Canonical or source URL within the approved website scope")
    snippet: str = Field(description="Grounded source text excerpt supporting the claim")


class ConversationTurn(BaseModel):
    """A single bounded turn in recent conversation context."""

    role: str = Field(
        description="Turn speaker: 'user' or 'assistant'.",
        pattern="^(user|assistant)$",
    )
    content: str = Field(
        description="Turn message content (max 1,000 characters).",
        min_length=1,
        max_length=1000,
    )


class ChatRequest(BaseModel):
    """Incoming user chat inquiry."""

    message: str = Field(
        description="The visitor's question text (max 2,000 characters).",
        min_length=1,
        max_length=2000,
    )
    session_id: Optional[str] = Field(
        default=None,
        description="Optional opaque client session ID for client-side state correlation.",
        max_length=128,
    )
    language: str = Field(
        default="auto",
        description="Target language or 'auto' to preserve the language of the inquiry.",
        max_length=16,
    )
    conversation_history: Optional[list[ConversationTurn]] = Field(
        default=None,
        description="Optional recent conversation turns (max 6) for resolving contextual pronouns like 'they' or 'it'.",
    )

    @field_validator("message")
    @classmethod
    def validate_message(cls, v: str) -> str:
        clean = v.strip()
        if not clean:
            raise ValueError("Message cannot be empty or whitespace-only.")
        if len(clean) > 2000:
            raise ValueError("Message exceeds maximum allowed limit of 2,000 characters.")
        return clean

    @field_validator("session_id")
    @classmethod
    def validate_session_id(cls, v: Optional[str]) -> Optional[str]:
        if v is None:
            return None
        clean = v.strip()
        if not clean:
            return None
        # Disallow control characters or excessively long values
        if any(c in clean for c in "\r\n\t\x00"):
            raise ValueError("Invalid session_id: control characters not permitted.")
        return clean

    @field_validator("conversation_history")
    @classmethod
    def validate_conversation_history(
        cls, v: Optional[list[ConversationTurn]]
    ) -> Optional[list[ConversationTurn]]:
        if v is None:
            return None
        # Enforce maximum bounds: limit to most recent 6 turns
        if len(v) > 6:
            v = v[-6:]
        return v



class ChatResponse(BaseModel):
    """Standardized response from the chat endpoint."""

    request_id: str = Field(description="Unique server-generated request correlation identifier.")
    answer: str = Field(description="Grounded answer text or polite fallback message.")
    status: ChatStatus = Field(description="Logical resolution status.")
    sources: list[SourceItem] = Field(
        default_factory=list,
        description="List of verified, non-duplicate citations from retrieved website metadata.",
    )
    quick_replies: list[str] = Field(
        default_factory=list,
        description="Contextual quick-reply chips for clarification or next steps.",
    )
    message: Optional[str] = Field(
        default=None,
        description="Optional operational or contextual notification.",
    )
