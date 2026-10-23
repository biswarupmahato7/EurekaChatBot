"""
backend/app/rag/citations.py
============================
Citation building and URL validation for grounded RAG answers.
Follows Problem Statement §8.6, §11.3 and Architecture §6.5.
"""
from __future__ import annotations

import logging
import re
from urllib.parse import urlparse

from backend.app.schemas.chat import SourceItem
from backend.app.schemas.chat import SourceItem
from backend.retrieval.models import SearchResult

logger = logging.getLogger(__name__)

# Default allowed domains for citations
APPROVED_DOMAINS: tuple[str, ...] = ("eurekasolutions.in", "www.eurekasolutions.in")


def is_safe_and_approved_url(
    url: str,
    allowed_domains: tuple[str, ...] = APPROVED_DOMAINS,
) -> bool:
    """Validate that a URL uses http/https, has no credentials, and matches an approved domain."""
    if not url or not isinstance(url, str):
        return False

    url_str = url.strip()
    # Reject dangerous protocols and formatting
    if any(url_str.lower().startswith(p) for p in ("javascript:", "data:", "file:", "vbscript:", "ftp:")):
        return False

    try:
        parsed = urlparse(url_str)
        if parsed.scheme not in ("http", "https"):
            return False

        if not parsed.netloc:
            return False

        # Reject embedded credentials (user:pass@host)
        if "@" in parsed.netloc:
            return False

        # Normalize hostname (lowercase, strip port if any)
        hostname = (parsed.hostname or "").lower()
        if not hostname:
            return False

        # Check domain allow-list
        if not any(hostname == domain or hostname.endswith("." + domain) for domain in allowed_domains):
            return False

        return True
    except Exception as exc:
        logger.warning("Error parsing citation URL %s: %s", url_str, exc)
        return False


def create_snippet_from_text(text: str, max_chars: int = 240) -> str:
    """Extract a clean, concise, grounded snippet from chunk text."""
    if not text:
        return ""
    # Collapse whitespace
    clean = " ".join(text.split()).strip()
    if len(clean) <= max_chars:
        return clean

    # Truncate at word boundary
    truncated = clean[:max_chars]
    last_space = truncated.rfind(" ")
    if last_space > 100:
        truncated = truncated[:last_space]
    return truncated + "..."


def build_citations_from_results(
    results: list[SearchResult],
    max_citations: int = 5,
    allowed_domains: tuple[str, ...] = APPROVED_DOMAINS,
) -> list[SourceItem]:
    """
    Build validated, deduplicated SourceItem citations from retrieved SearchResult items.
    
    Guarantees:
    - Never invents URLs or excerpts.
    - Rejects unsafe or non-approved URLs.
    - Deduplicates page-level URLs, keeping the chunk with highest relevance.
    """
    seen_urls: set[str] = set()
    citations: list[SourceItem] = []

    for item in results:
        meta = getattr(item, "metadata", {}) or {}
        raw_url = str(
            getattr(item, "source_url", "")
            or getattr(item, "url", "")
            or meta.get("source_url")
            or meta.get("url")
            or ""
        ).strip()

        if not raw_url:
            continue

        if not is_safe_and_approved_url(raw_url, allowed_domains):
            logger.warning("Rejected non-approved or unsafe citation URL: %s", raw_url)
            continue

        # Normalize URL key for deduplication (strip fragment, then trailing slash)
        norm_url_key = raw_url.split("#")[0].rstrip("/").lower()
        if norm_url_key in seen_urls:
            continue
        seen_urls.add(norm_url_key)

        title = str(
            getattr(item, "page_title", "")
            or getattr(item, "title", "")
            or meta.get("page_title")
            or meta.get("title")
            or getattr(item, "section_heading", "")
            or "Eureka Solutions"
        ).strip()
        if not title:
            title = "Eureka Solutions"

        raw_text = getattr(item, "text", "") or getattr(item, "chunk_text", "") or meta.get("chunk_text") or ""
        snippet = create_snippet_from_text(raw_text)

        citations.append(
            SourceItem(
                title=title,
                url=raw_url,
                snippet=snippet,
            )
        )

        if len(citations) >= max_citations:
            break

    return citations


def sanitize_markdown_links_in_answer(
    answer: str,
    valid_citations: list[SourceItem],
) -> str:
    """
    Inspect markdown links in the generated LLM answer: [text](url).
    If a link targets an unapproved URL or a URL not present in valid_citations,
    strip the link and keep only the anchor text to prevent link hallucination / phishing.
    """
    valid_urls = {c.url.strip() for c in valid_citations}

    def _replace_link(match: re.Match) -> str:
        anchor_text = match.group(1)
        target_url = match.group(2).strip()
        if target_url in valid_urls or is_safe_and_approved_url(target_url):
            return match.group(0)
        # Stripping unapproved or hallucinated link
        return anchor_text

    link_pattern = re.compile(r"\[([^\]]+)\]\(([^)]+)\)")
    return link_pattern.sub(_replace_link, answer)


def strip_inline_citations(text: str) -> str:
    """
    Remove inline citation markers (e.g. [Source 1], [1], [Source: ...]) and trailing
    Sources/References sections while preserving meaningful bracketed text and numbered lists.
    """
    if not text:
        return ""

    cleaned = text

    # Remove trailing References / Sources section
    trailing_sources_section_regex = (
        r"(?:\r?\n)+(?:#{1,6}\s*|\*{1,2})?(?:Sources|References|Citations)(?:\*{1,2}|:)*\s*(?:\r?\n+[\s\S]*)$"
    )

    def _clean_trailing(match: re.Match) -> str:
        matched_str = match.group(0)
        # Check if the trailing block contains citation indicators
        if re.search(r"https?://|\[Source|\burl\b|www\.|\d+\.\s+|-\s+", matched_str, re.IGNORECASE):
            return ""
        return matched_str

    cleaned = re.sub(trailing_sources_section_regex, _clean_trailing, cleaned, flags=re.IGNORECASE)

    # Remove inline source markers like [Source 1], [Source 1, 2], [Source: ...]
    cleaned = re.sub(
        r"\s*\[(?:Sources?|Ref|Reference)(?::\s*[^\]\n]+|\s*\d+(?:[\s,;–-]+(?:and\s*)?(?:Sources?\s*)?\d+)*)\](?!\()",
        "",
        cleaned,
        flags=re.IGNORECASE,
    )

    # Remove inline numeric citation markers like [1], [2], [1, 2]
    # Guard against word characters before [ (e.g. array[0]), years [2024-2026], and links [1](...)
    cleaned = re.sub(
        r"(?<![\w$])\s*\[\s*\d{1,2}(?:\s*[,;–-]\s*\d{1,2})*\s*\](?!\()",
        "",
        cleaned,
    )

    # Clean up whitespace before punctuation and multiple periods
    cleaned = re.sub(r"\s+([.,;:!?])", r"\1", cleaned)
    cleaned = re.sub(r"\.{2,}", ".", cleaned)
    cleaned = re.sub(r"(?<=\S)[^\S\r\n]{2,}", " ", cleaned)
    return cleaned.strip()


VERIFIED_CONTACT_EMAIL = "info@eurekasolutions.in"


def sanitize_contact_details(text: str) -> str:
    """
    Enforce contact information integrity on assistant output:
    1. Disallow invented or unapproved email addresses. Replace or normalize them to info@eurekasolutions.in.
    2. Disallow unverified phone numbers or malicious contact injections.
    3. Rephrase generic 'visit our website' / 'check our website' instructions because the assistant
       is embedded on the website itself.
    """
    if not text:
        return ""

    cleaned = text

    # 1. Normalize/sanitize any non-whitelisted email address to info@eurekasolutions.in
    def _replace_email(match: re.Match) -> str:
        email = match.group(0).lower()
        if email == VERIFIED_CONTACT_EMAIL.lower():
            return match.group(0)
        return VERIFIED_CONTACT_EMAIL

    cleaned = re.sub(r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b", _replace_email, cleaned)

    # 2. Sanitize unverified phone numbers (>= 10 digits formatted as telephone)
    phone_pattern = re.compile(r"(?:\+?\d{1,3}[-.\s]?)?\(?\d{3,4}\)?[-.\s]?\d{3,4}[-.\s]?\d{3,4}\b")

    def _sanitize_phone(match: re.Match) -> str:
        matched = match.group(0)
        digits = re.sub(r"\D", "", matched)
        if len(digits) >= 10:
            return VERIFIED_CONTACT_EMAIL
        return matched

    cleaned = phone_pattern.sub(_sanitize_phone, cleaned)

    # 3. Clean up unhelpful 'visit our website' advice since visitor is on the website
    cleaned = re.sub(
        r"\b(?:please\s+)?(?:visit|check|browse)\s+(?:the|our)\s+official\s+(?:eureka\s+solutions\s+)?website(?:\s+at\s+https?://[^\s,]+)?(?:\s+or\s+use\s+its\s+contact\s+forms?)?[,\s]*",
        "reach out directly to info@eurekasolutions.in ",
        cleaned,
        flags=re.IGNORECASE,
    )
    cleaned = re.sub(
        r"\b(?:visit|check)\s+(?:the|our)\s+website[,\s]*",
        "contact our team ",
        cleaned,
        flags=re.IGNORECASE,
    )
    cleaned = re.sub(
        r"\bon\s+(?:the|our)\s+website['’]?s?\s+(?:contact|enquiry)\s+(?:forms?|options?)[,\s]*",
        "by emailing info@eurekasolutions.in ",
        cleaned,
        flags=re.IGNORECASE,
    )

    cleaned = re.sub(r"[ \t]{2,}", " ", cleaned)
    return cleaned.strip()
