"""
crawler/tests/test_smoke.py
============================
Phase 0 smoke tests for the Eureka RAG Chatbot crawler package.

These tests verify that:
  1. The Python test environment is operational.
  2. The crawler package is importable as a Python package.
  3. Key Phase A dependency libraries are installed and importable.
  4. Basic URL normalization logic works correctly without network access.

CONSTRAINTS:
  - No network calls (no live website access).
  - No API keys required (Groq, embedding, vector DB).
  - No running backend required.
  - Deterministic: same result every run.
  - Discovered automatically by pytest from the repository root.
"""

import sys
import importlib


# ─────────────────────────────────────────────────────────────────────────────
# 1. Environment sanity checks
# ─────────────────────────────────────────────────────────────────────────────


def test_python_version_is_311_or_newer() -> None:
    """Python 3.11+ is required by the project specification (PS §7.1)."""
    major, minor = sys.version_info.major, sys.version_info.minor
    assert (major, minor) >= (3, 11), (
        f"Python 3.11 or newer is required. Running: {sys.version}"
    )


# ─────────────────────────────────────────────────────────────────────────────
# 2. Crawler package importability
# ─────────────────────────────────────────────────────────────────────────────


def test_crawler_package_is_importable() -> None:
    """The crawler package must be importable as a Python package."""
    crawler = importlib.import_module("crawler")
    assert crawler is not None


# ─────────────────────────────────────────────────────────────────────────────
# 3. Crawler dependency availability
#    Verifies that all libraries listed in crawler/requirements.txt are
#    installed. Tests fail with a clear message if a dependency is missing.
# ─────────────────────────────────────────────────────────────────────────────


def test_requests_is_importable() -> None:
    """requests — HTTP client for the crawler fetcher."""
    import requests  # noqa: F401


def test_beautifulsoup4_is_importable() -> None:
    """beautifulsoup4 — HTML parser for content extraction."""
    import bs4  # noqa: F401


def test_pydantic_is_importable() -> None:
    """pydantic v2 — schema validation for crawler data models."""
    import pydantic  # noqa: F401
    assert int(pydantic.VERSION.split(".")[0]) >= 2, (
        f"Pydantic v2+ required. Installed: {pydantic.VERSION}"
    )


def test_tiktoken_is_importable() -> None:
    """tiktoken — tokenizer for chunk token counting (PS §7.1, architecture §4.1)."""
    import tiktoken  # noqa: F401


def test_dotenv_is_importable() -> None:
    """python-dotenv — local environment configuration loader."""
    import dotenv  # noqa: F401


# ─────────────────────────────────────────────────────────────────────────────
# 4. Standard-library URL utilities (always available — no install needed)
# ─────────────────────────────────────────────────────────────────────────────


def test_urllib_parse_is_importable() -> None:
    """urllib.parse — URL normalization and manipulation (stdlib)."""
    from urllib import parse  # noqa: F401


def test_urllib_robotparser_is_importable() -> None:
    """urllib.robotparser — robots.txt parsing (stdlib)."""
    from urllib import robotparser  # noqa: F401


# ─────────────────────────────────────────────────────────────────────────────
# 5. Lightweight URL normalization logic
#    These tests exercise actual normalization logic using only Python stdlib.
#    No network access. No production modules required.
#    They form a stable foundation for Phase A URL utilities.
# ─────────────────────────────────────────────────────────────────────────────

from urllib.parse import urlparse, urlunparse, urljoin


def _normalize_url(url: str) -> str:
    """
    Minimal URL normalization for smoke-test purposes.

    Applies:
      - Lowercase scheme and host
      - Strip URL fragment (hash)
      - Ensure trailing slash on bare paths
      - Strip default HTTP/HTTPS ports

    This is a test fixture, NOT the production URL utility (Phase A).
    """
    parsed = urlparse(url.strip())
    scheme = parsed.scheme.lower()
    netloc = parsed.netloc.lower()

    # Strip default ports
    if ":" in netloc:
        host, port = netloc.rsplit(":", 1)
        if (scheme == "http" and port == "80") or (scheme == "https" and port == "443"):
            netloc = host

    path = parsed.path or "/"
    # Normalise path: ensure at least "/"
    if not path:
        path = "/"

    # Drop fragment; keep query for this minimal normalizer
    normalized = urlunparse((scheme, netloc, path, parsed.params, parsed.query, ""))
    return normalized


def test_url_normalization_strips_fragment() -> None:
    """Fragment (#section) must be stripped from crawl URLs."""
    result = _normalize_url("https://eurekasolutions.in/Eureka2026/services/#section")
    assert "#" not in result, f"Fragment not stripped: {result}"


def test_url_normalization_lowercases_host() -> None:
    """Host must be lowercased for deduplication."""
    result = _normalize_url("HTTPS://EurekaSolutions.IN/Eureka2026/")
    assert "eurekasolutions.in" in result


def test_url_normalization_strips_default_https_port() -> None:
    """Default HTTPS port 443 must be stripped."""
    result = _normalize_url("https://eurekasolutions.in:443/Eureka2026/")
    assert ":443" not in result


def test_url_normalization_strips_default_http_port() -> None:
    """Default HTTP port 80 must be stripped."""
    result = _normalize_url("http://eurekasolutions.in:80/path/")
    assert ":80" not in result


def test_crawl_scope_enforcement_in_scope() -> None:
    """URLs within the approved scope must be accepted."""
    approved_origin = "eurekasolutions.in"
    approved_prefix = "/Eureka2026/"
    test_urls = [
        "https://eurekasolutions.in/Eureka2026/",
        "https://eurekasolutions.in/Eureka2026/services/",
        "https://eurekasolutions.in/Eureka2026/about/",
    ]
    for url in test_urls:
        parsed = urlparse(url)
        assert parsed.netloc == approved_origin, f"Host mismatch: {url}"
        assert parsed.path.startswith(approved_prefix), f"Path out of scope: {url}"


def test_crawl_scope_enforcement_out_of_scope() -> None:
    """External URLs must NOT be treated as in-scope."""
    approved_origin = "eurekasolutions.in"
    approved_prefix = "/Eureka2026/"
    out_of_scope_urls = [
        "https://google.com/search?q=eureka",
        "https://otherdomain.com/Eureka2026/",
        "https://eurekasolutions.in/other-path/",
    ]
    for url in out_of_scope_urls:
        parsed = urlparse(url)
        in_scope = (
            parsed.netloc == approved_origin
            and parsed.path.startswith(approved_prefix)
        )
        assert not in_scope, f"URL incorrectly classified as in-scope: {url}"


def test_tiktoken_encoding_loads_and_counts_tokens() -> None:
    """
    tiktoken must load the default encoding and produce a non-zero token count.
    This validates the tokenizer is correctly installed and functional.

    The cl100k_base encoding is the configured default (see .env.example
    TOKENIZER setting). Token counts are encoding-dependent — consistent
    use of the same encoding throughout the pipeline is required.
    """
    import tiktoken

    enc = tiktoken.get_encoding("cl100k_base")
    tokens = enc.encode("Eureka Solutions provides enterprise software services.")
    assert len(tokens) > 0, "tiktoken returned zero tokens for a non-empty string"
    # Sanity: a typical English sentence should tokenize to fewer than 30 tokens
    assert len(tokens) < 30, f"Unexpectedly high token count: {len(tokens)}"


def test_pydantic_model_validation_works() -> None:
    """
    Pydantic v2 must be able to define and validate a simple model.
    This validates the schema-validation foundation for Phase A data models.
    """
    from pydantic import BaseModel, HttpUrl, field_validator

    class _PageRecord(BaseModel):
        page_id: str
        source_url: str
        title: str | None = None

        @field_validator("page_id")
        @classmethod
        def page_id_must_not_be_empty(cls, v: str) -> str:
            if not v.strip():
                raise ValueError("page_id must not be empty")
            return v

    # Valid record
    record = _PageRecord(
        page_id="abc123",
        source_url="https://eurekasolutions.in/Eureka2026/",
        title="Home",
    )
    assert record.page_id == "abc123"
    assert record.title == "Home"

    # Invalid record (empty page_id) must raise
    import pytest

    with pytest.raises(Exception):
        _PageRecord(page_id="   ", source_url="https://eurekasolutions.in/Eureka2026/")
