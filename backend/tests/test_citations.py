"""
backend/tests/test_citations.py
===============================
Unit tests for URL validation, snippet extraction, and citation deduplication.
"""
from backend.app.rag.citations import (
    build_citations_from_results,
    create_snippet_from_text,
    is_safe_and_approved_url,
    sanitize_markdown_links_in_answer,
    strip_inline_citations,
)
from backend.retrieval.models import SearchResult


def test_is_safe_and_approved_url():
    # Valid approved URLs
    assert is_safe_and_approved_url("https://eurekasolutions.in/Eureka2026/services/")
    assert is_safe_and_approved_url("http://www.eurekasolutions.in/about")

    # Reject dangerous protocols
    assert not is_safe_and_approved_url("javascript:alert(1)")
    assert not is_safe_and_approved_url("data:text/html,<html>")
    assert not is_safe_and_approved_url("file:///etc/passwd")

    # Reject foreign domains
    assert not is_safe_and_approved_url("https://malicious-site.com/steal")
    assert not is_safe_and_approved_url("https://google.com")

    # Reject embedded credentials
    assert not is_safe_and_approved_url("https://user:pass@eurekasolutions.in/")


def test_create_snippet_from_text():
    text = "Eureka Solutions is a premier technology consultancy. We build advanced software and AI integrations for global enterprises."
    snippet = create_snippet_from_text(text, max_chars=50)
    assert len(snippet) <= 53  # including ellipsis
    assert snippet.endswith("...")
    assert "Eureka Solutions" in snippet

    # Short text preserved without ellipsis
    short = "Short text."
    assert create_snippet_from_text(short, max_chars=100) == "Short text."


def test_build_citations_deduplication_and_safety():
    results = [
        SearchResult(
            chunk_id="chunk-1",
            page_id="page-1",
            text="First chunk from services page.",
            source_url="https://eurekasolutions.in/Eureka2026/services/",
            page_title="Services",
            score=0.9,
        ),
        SearchResult(
            chunk_id="chunk-2",
            page_id="page-1",
            text="Second chunk from same services page.",
            source_url="https://eurekasolutions.in/Eureka2026/services/#section2",
            page_title="Services",
            score=0.8,
        ),
        SearchResult(
            chunk_id="chunk-3",
            page_id="page-2",
            text="Dangerous link candidate.",
            source_url="javascript:alert(1)",
            page_title="Evil",
            score=0.95,
        ),
        SearchResult(
            chunk_id="chunk-4",
            page_id="page-3",
            text="About Us details.",
            source_url="https://eurekasolutions.in/Eureka2026/about/",
            page_title="About Us",
            score=0.85,
        ),
    ]

    citations = build_citations_from_results(results, max_citations=5)

    # Chunk-2 is duplicate of page-1, chunk-3 is rejected unsafe link
    assert len(citations) == 2
    assert citations[0].url == "https://eurekasolutions.in/Eureka2026/services/"
    assert citations[1].url == "https://eurekasolutions.in/Eureka2026/about/"
    assert "First chunk from services page." in citations[0].snippet


def test_sanitize_markdown_links_in_answer():
    results = [
        SearchResult(
            chunk_id="c1",
            page_id="p1",
            text="Content",
            source_url="https://eurekasolutions.in/Eureka2026/services/",
            page_title="Services",
        )
    ]
    citations = build_citations_from_results(results)

    raw_answer = (
        "Check our [Services](https://eurekasolutions.in/Eureka2026/services/) or visit "
        "[Phishing](https://phishing-site.com/login) to log in."
    )
    cleaned = sanitize_markdown_links_in_answer(raw_answer, citations)

    # Approved link remains active
    assert "[Services](https://eurekasolutions.in/Eureka2026/services/)" in cleaned
    # Unapproved external link stripped to anchor text only
    assert "visit Phishing to log in." in cleaned
    assert "phishing-site.com" not in cleaned


def test_strip_inline_citations():
    # 1. Strips [Source 1], [Source 2], [Source 1, 2]
    raw = "Eureka Solutions is an award-winning NetSuite partner [Source 1]. We provide ERP [Source 1, 2]."
    cleaned = strip_inline_citations(raw)
    assert cleaned == "Eureka Solutions is an award-winning NetSuite partner. We provide ERP."

    # 2. Strips [1], [2], [Source: ...]
    raw2 = "Our services include cloud integration [1] and agentic AI [Source: Case Study]."
    cleaned2 = strip_inline_citations(raw2)
    assert cleaned2 == "Our services include cloud integration and agentic AI."

    # 3. Strips trailing Sources section
    raw3 = (
        "We offer ERP and CRM solutions.\n\n"
        "### Sources\n"
        "- [Source 1] NetSuite: https://eurekasolutions.in/services\n"
        "- [Source 2] Cloud: https://eurekasolutions.in/cloud"
    )
    cleaned3 = strip_inline_citations(raw3)
    assert cleaned3 == "We offer ERP and CRM solutions."
    assert "Sources" not in cleaned3
    assert "https://" not in cleaned3

    # 4. Preserves meaningful bracketed text
    raw4 = "System status: [CRITICAL]. Version: [v2.1.0]. Target years: [2024-2026]."
    cleaned4 = strip_inline_citations(raw4)
    assert cleaned4 == "System status: [CRITICAL]. Version: [v2.1.0]. Target years: [2024-2026]."

    # 5. Preserves array indexing and markdown links
    raw5 = "Check array[0] configuration and see [Services](https://eurekasolutions.in/services)."
    cleaned5 = strip_inline_citations(raw5)
    assert cleaned5 == "Check array[0] configuration and see [Services](https://eurekasolutions.in/services)."

    # 6. Preserves ordered lists
    raw6 = "Here are the steps:\n1. Assessment\n2. Implementation\n3. Support"
    cleaned6 = strip_inline_citations(raw6)
    assert cleaned6 == "Here are the steps:\n1. Assessment\n2. Implementation\n3. Support"
