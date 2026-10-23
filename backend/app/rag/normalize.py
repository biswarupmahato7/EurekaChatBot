"""
backend/app/rag/normalize.py
============================
Query normalization module.

Cleans superfluous whitespace and normalizes Unicode while preserving the user's
semantic intent, language, proper nouns, and safety-relevant context.
"""
from __future__ import annotations

import re
import unicodedata


def normalize_query(text: str) -> str:
    """Normalize user question text safely without altering semantic intent."""
    if not text:
        return ""

    # Normalize Unicode composition (NFC)
    normalized = unicodedata.normalize("NFC", text)

    # Convert Windows / Mac linebreaks to standard space
    normalized = normalized.replace("\r\n", " ").replace("\r", " ").replace("\n", " ")

    # Collapse multiple whitespace characters into single space
    normalized = re.sub(r"\s+", " ", normalized)

    return normalized.strip()
