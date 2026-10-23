"""
backend/app/rag/reference_resolver.py
=====================================
Contextual reference and pronoun resolution for follow-up questions.
Follows Problem Statement and Task Requirements §5:
- Resolves contextual pronouns ('they', 'their', 'them', 'it', 'its', 'that service').
- Preserves user's actual intent.
- Uses conversation history strictly for query contextualization, NEVER as authoritative evidence.
- Stateless, bounded, and privacy-conscious (no external database).
"""
from __future__ import annotations

import re
from typing import Optional

from backend.app.schemas.chat import ConversationTurn

# Patterns identifying third-person company referents
_COMPANY_PRONOUN_PATTERNS = [
    (re.compile(r"\bdo\s+they\b", re.I), "does Eureka Solutions"),
    (re.compile(r"\bare\s+they\b", re.I), "is Eureka Solutions"),
    (re.compile(r"\bcan\s+they\b", re.I), "can Eureka Solutions"),
    (re.compile(r"\bhave\s+they\b", re.I), "has Eureka Solutions"),
    (re.compile(r"\bwill\s+they\b", re.I), "will Eureka Solutions"),
    (re.compile(r"\bdid\s+they\b", re.I), "did Eureka Solutions"),
    (re.compile(r"\btheir\b", re.I), "Eureka Solutions'"),
    (re.compile(r"\bthem\b", re.I), "Eureka Solutions"),
]

# Known verified service keywords to extract as referent targets
_KNOWN_SERVICES = [
    "Agentic AI",
    "AI Strategy",
    "AI Chatbots",
    "WhatsApp Bot",
    "WhatsApp Service Bot",
    "Enterprise ERP",
    "ERP Solutions",
    "Cloud Infrastructure",
    "Cloud Migration",
    "Enterprise Software",
]


def _extract_recent_service(conversation_history: Optional[list[ConversationTurn]]) -> Optional[str]:
    """Find the most recently discussed service topic in conversation history."""
    if not conversation_history:
        return None
    for turn in reversed(conversation_history):
        content_lower = turn.content.lower()
        for service in _KNOWN_SERVICES:
            if service.lower() in content_lower:
                return service
    return None



_LOCATION_KEYWORDS = re.compile(
    r"\b(office|offices|location|locations|headquarters|based|city|cities|presence|branch|branches)\b",
    re.I,
)


def has_recent_location_context(conversation_history: Optional[list[ConversationTurn]]) -> bool:
    """Return True if recent conversation history explicitly discusses offices or locations."""
    if not conversation_history:
        return False
    for turn in reversed(conversation_history[-4:]):
        content = turn.content if hasattr(turn, "content") else (turn.get("content", "") if isinstance(turn, dict) else "")
        if _LOCATION_KEYWORDS.search(content):
            return True
    return False


_ELLIPTICAL_PATTERNS = [
    re.compile(r"^(what\s+about|how\s+about|and|any)\s+(an?\s+office\s+in|offices?\s+in|presence\s+in|locations?\s+in)\s+([a-zA-Z\s]+)\??$", re.I),
    re.compile(r"^(what\s+about|how\s+about|and)\s+in\s+([a-zA-Z\s]+)\??$", re.I),
]


def resolve_query_context(
    query: str,
    conversation_history: Optional[list[ConversationTurn]] = None,
) -> str:
    """
    Resolve anaphoric and contextual references in the user query for search retrieval.
    
    If the current question uses 'they', 'their', 'them', 'it', or elliptical phrasing
    referring to the company or service, rewrite the query to explicitly refer to
    Eureka Solutions or the service topic so that dense vector retrieval finds relevant chunks.
    
    Returns the contextualized query string.
    """
    clean = query.strip()
    if not clean:
        return clean

    # 1. Check for elliptical location follow-ups (e.g. "What about in Goa?", "And in Goa?")
    for pattern in _ELLIPTICAL_PATTERNS:
        match = pattern.match(clean)
        if match:
            location = match.group(match.lastindex).strip()
            return f"Does Eureka Solutions have an office or presence in {location}?"

    # 1b. Check for short location queries (e.g. "Goa?" or "in Goa?") when preceded by location context
    if has_recent_location_context(conversation_history) and len(clean.split()) <= 2:
        m = re.match(r"^(in\s+)?([a-zA-Z\s]{2,20})\??$", clean)
        if m:
            place = m.group(2).strip()
            if place.lower() not in {"yes", "no", "ok", "okay", "sure", "thanks", "thank you", "hello", "hi"}:
                return f"Does Eureka Solutions have an office or presence in {place}?"

    # 2. Extract recent service if discussed
    recent_service = _extract_recent_service(conversation_history)
    subject = recent_service or "Eureka Solutions"

    # 3. Check if query refers to 'it', 'its', or 'that service'
    it_patterns = [
        (re.compile(r"\bcan\s+it\b", re.I), f"can {subject}"),
        (re.compile(r"\bdoes\s+it\b", re.I), f"does {subject}"),
        (re.compile(r"\bis\s+it\b", re.I), f"is {subject}"),
        (re.compile(r"\bhas\s+it\b", re.I), f"has {subject}"),
        (re.compile(r"\bwill\s+it\b", re.I), f"will {subject}"),
        (re.compile(r"\bdid\s+it\b", re.I), f"did {subject}"),
        (re.compile(r"\bits\b", re.I), f"{subject}'s"),
        (re.compile(r"\bthat\s+service\b", re.I), f"{subject}"),
        (re.compile(r"\bthis\s+service\b", re.I), f"{subject}"),
    ]

    resolved = clean
    has_pronoun = False

    # Check 'it' references if we have service or company context
    if conversation_history:
        for pattern, replacement in it_patterns:
            if pattern.search(resolved):
                resolved = pattern.sub(replacement, resolved)
                has_pronoun = True

    # 4. Check company pronoun references ('they', 'their', 'them')
    for pattern, replacement in _COMPANY_PRONOUN_PATTERNS:
        if pattern.search(resolved):
            resolved = pattern.sub(replacement, resolved)
            has_pronoun = True

    # If the query had pronouns replaced, clean up any double spaces or punctuation
    if has_pronoun:
        resolved = re.sub(r"\s+", " ", resolved).strip()
        return resolved

    # If the query is a short follow-up starting with "what about" or "how about"
    # e.g., "What about AI services?" -> "What about Eureka Solutions' AI services?"
    if re.match(r"^(what\s+about|how\s+about)\s+", clean, re.I) and "eureka" not in clean.lower():
        sub_topic = re.sub(r"^(what\s+about|how\s+about)\s+", "", clean, flags=re.I).strip()
        if sub_topic:
            return f"What about Eureka Solutions {sub_topic}"

    return clean
