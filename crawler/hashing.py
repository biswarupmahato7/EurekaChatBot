"""
crawler/hashing.py
==================
SHA-256 content hashing and deterministic stable identifiers.

Rules (documented in architecture §4.4 / PS §7.2):
- page_id: SHA-256 of the normalized canonical URL (or source URL if canonical
  is absent/untrusted). Hex-encoded, first 16 chars used as a short prefix
  followed by full hash to ensure global uniqueness.
- content_hash: SHA-256 of normalized extracted content + title (stripped,
  unicode-normalised). Changes when meaningful content changes.
- chunk_id: SHA-256 of page_id + chunk_index (zero-padded) + chunking_version.

IMPORTANT: Python's built-in hash() is randomised per-process and MUST NOT
be used for any persistent identifier. Only hashlib.sha256 is used here.
"""
from __future__ import annotations

import hashlib
import unicodedata


# ── URL / page identity ──────────────────────────────────────────────────────

def _norm_url_for_hash(url: str) -> str:
    """Strip trailing slash, lowercase scheme+host, strip fragment."""
    url = url.strip()
    # Remove fragment
    if "#" in url:
        url = url[: url.index("#")]
    # Lowercase scheme and host
    if "://" in url:
        scheme, rest = url.split("://", 1)
        if "/" in rest:
            host, path = rest.split("/", 1)
            url = f"{scheme.lower()}://{host.lower()}/{path}"
        else:
            url = f"{scheme.lower()}://{rest.lower()}"
    # Strip trailing slash from path (but keep scheme://)
    if url.endswith("/") and url.count("/") > 2:
        url = url.rstrip("/")
    return url


def make_page_id(canonical_url: str | None, source_url: str) -> str:
    """Return a stable hex page_id derived from the best available URL.

    Prefer canonical_url when it is a non-empty, non-self-referential value.
    Fall back to source_url otherwise.
    """
    url = (canonical_url or "").strip() or source_url
    normed = _norm_url_for_hash(url)
    return hashlib.sha256(normed.encode("utf-8")).hexdigest()


# ── Content hash ─────────────────────────────────────────────────────────────

def _normalise_text(text: str) -> str:
    """Unicode-normalise and strip text for stable hashing."""
    return unicodedata.normalize("NFC", text).strip()


def make_content_hash(content: str, title: str = "") -> str:
    """Return a SHA-256 hex hash of normalised content + title.

    A change in extracted text or title will change this hash.
    Formatting-only changes in this module must NOT change this value.
    """
    normalised = _normalise_text(content) + "\n" + _normalise_text(title)
    return hashlib.sha256(normalised.encode("utf-8")).hexdigest()


# ── Chunk identity ────────────────────────────────────────────────────────────

def make_chunk_id(page_id: str, chunk_index: int, chunking_version: str) -> str:
    """Return a deterministic chunk_id.

    Inputs: page_id (hex), zero-padded chunk_index (6 digits), chunking_version.
    A change in any input produces a different chunk_id.
    """
    raw = f"{page_id}:{chunk_index:06d}:{chunking_version}"
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def make_chunk_content_hash(content: str) -> str:
    """SHA-256 of the chunk's exact content (NFC-normalised)."""
    return hashlib.sha256(_normalise_text(content).encode("utf-8")).hexdigest()
