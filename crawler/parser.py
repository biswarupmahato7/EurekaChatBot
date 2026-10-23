"""
crawler/parser.py
=================
HTML parser and content cleaner for the Eureka RAG Chatbot crawler.

DESIGN RULE: This module makes NO network requests.
It receives already-fetched HTML text and returns structured PageRecord data.

A.0 Inspection findings:
- Most content pages have <main> tag
- Homepage (/Eureka2026/) has no <main>, uses body fallback
- Pages are server-rendered — full content in static HTML
- No Playwright needed
- Navigation menu is duplicated across pages (must be removed)
"""
from __future__ import annotations

import logging
import re
from datetime import datetime, timezone
from typing import Optional
from urllib.parse import urljoin, urlparse

from bs4 import BeautifulSoup, NavigableString, Tag

from crawler.models import ContentBlock, Heading, PageRecord
from crawler.hashing import make_page_id, make_content_hash
from crawler.url_utils import normalize_url, is_in_scope

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Boilerplate patterns to strip
# ---------------------------------------------------------------------------
_BOILERPLATE_TAGS: tuple[str, ...] = (
    "script", "style", "noscript", "iframe", "svg", "canvas",
    "meta", "link", "head",
)

_COOKIE_BANNER_CLASSES: tuple[str, ...] = (
    "cookie", "gdpr", "consent", "privacy-banner", "cc-banner",
    "cookie-notice", "cookie-bar",
)

_NAV_TAGS: tuple[str, ...] = ("nav", "header", "footer")

_EMPTY_CONTENT_THRESHOLD = 100  # characters below which page is "low content"

# Repeated whitespace cleaner
_WS_RE = re.compile(r"[ \t]+")
_MULTI_NL_RE = re.compile(r"\n{3,}")

# Junk symbol patterns (emoji replacement artifacts)
_JUNK_CHARS_RE = re.compile(r"[\ufffd\u2014\u2013\u2018\u2019\u201c\u201d\u2026]+")


# ===========================================================================
# Core parser
# ===========================================================================

class PageParser:
    """Stateless HTML → PageRecord parser.

    Usage:
        parser = PageParser(approved_origin="eurekasolutions.in",
                           approved_prefix="/Eureka2026/")
        record = parser.parse(html_text, source_url=url, final_url=url, http_status=200)
    """

    def __init__(
        self,
        approved_origin: str = "eurekasolutions.in",
        approved_prefix: str = "/Eureka2026/",
        extra_allowed_paths: list[str] | None = None,
    ) -> None:
        self.approved_origin = approved_origin
        self.approved_prefix = approved_prefix
        self.extra_allowed_paths = extra_allowed_paths or []

    # ── Public ────────────────────────────────────────────────────────────────

    def parse(
        self,
        html_text: str,
        source_url: str,
        final_url: str,
        http_status: Optional[int] = 200,
        crawl_timestamp: Optional[str] = None,
    ) -> PageRecord:
        """Parse html_text and return a populated PageRecord.

        All fields default to null/empty on extraction failure.
        Warnings are added to PageRecord.warnings; content is never invented.
        """
        warnings: list[str] = []
        ts = crawl_timestamp or datetime.now(timezone.utc).isoformat()

        soup = BeautifulSoup(html_text, "lxml")

        # ── Extract metadata ──────────────────────────────────────────────────
        title = self._extract_title(soup)
        meta_desc = self._extract_meta_description(soup)
        canonical_url = self._extract_canonical(soup, base_url=source_url)

        # ── Build page identity ───────────────────────────────────────────────
        page_id = make_page_id(canonical_url, source_url)

        # ── Extract headings ─────────────────────────────────────────────────
        headings = self._extract_headings(soup)

        # ── Clean and extract content ─────────────────────────────────────────
        if not soup.find("main"):
            warnings.append("no_main_tag: fallback to body/article extraction")
        content_area = self._find_content_area(soup)
        self._remove_boilerplate(content_area)

        content_blocks = self._extract_content_blocks(content_area)
        content_text = self._extract_text(content_area)

        # ── Quality checks ────────────────────────────────────────────────────
        is_empty = not content_text.strip()
        is_low_content = len(content_text.strip()) < _EMPTY_CONTENT_THRESHOLD

        if is_empty:
            warnings.append("empty_content: no text extracted from page")
        elif is_low_content:
            warnings.append(
                f"low_content: only {len(content_text.strip())} chars extracted"
            )

        if not title:
            warnings.append("missing_title")
        if not meta_desc:
            warnings.append("missing_meta_description")

        # ── Extract internal links ────────────────────────────────────────────
        internal_links = self._extract_internal_links(soup, base_url=final_url)

        # ── Content hash ──────────────────────────────────────────────────────
        content_hash = make_content_hash(content_text, title or "")

        return PageRecord(
            page_id=page_id,
            schema_version="1.0",
            source_url=source_url,
            canonical_url=canonical_url,
            final_url=final_url,
            title=title,
            meta_description=meta_desc,
            headings=headings,
            content=content_text,
            content_blocks=content_blocks,
            internal_links=internal_links,
            content_hash=content_hash,
            http_status=http_status,
            crawl_timestamp=ts,
            warnings=warnings,
            is_low_content=is_low_content,
            is_empty=is_empty,
        )

    # ── Extraction helpers ────────────────────────────────────────────────────

    def _extract_title(self, soup: BeautifulSoup) -> Optional[str]:
        tag = soup.find("title")
        if tag:
            return tag.get_text(strip=True) or None
        # Fallback: first H1
        h1 = soup.find("h1")
        if h1:
            return h1.get_text(strip=True) or None
        return None

    def _extract_meta_description(self, soup: BeautifulSoup) -> Optional[str]:
        meta = soup.find("meta", attrs={"name": re.compile(r"^description$", re.I)})
        if meta and meta.get("content"):
            return meta["content"].strip() or None
        return None

    def _extract_canonical(self, soup: BeautifulSoup, base_url: str = "") -> Optional[str]:
        link = soup.find("link", rel=re.compile(r"canonical", re.I))
        if link and link.get("href"):
            href = link["href"].strip()
            if href:
                resolved = urljoin(base_url, href)
                normed = normalize_url(resolved)
                return normed
        return None

    def _extract_headings(self, soup: BeautifulSoup) -> list[Heading]:
        headings: list[Heading] = []
        seen: set[str] = set()
        for tag_name in ("h1", "h2", "h3"):
            for tag in soup.find_all(tag_name):
                text = tag.get_text(strip=True)
                if text and text not in seen:
                    seen.add(text)
                    try:
                        headings.append(Heading(level=int(tag_name[1]), text=text))
                    except Exception:
                        pass
        # Sort by document order (find_all already returns in order — re-collect)
        headings_ordered: list[Heading] = []
        seen2: set[str] = set()
        for tag in soup.find_all(re.compile(r"^h[123]$")):
            text = tag.get_text(strip=True)
            key = f"{tag.name}:{text}"
            if text and key not in seen2:
                seen2.add(key)
                try:
                    headings_ordered.append(
                        Heading(level=int(tag.name[1]), text=text)
                    )
                except Exception:
                    pass
        return headings_ordered

    def _find_content_area(self, soup: BeautifulSoup) -> Tag:
        """Return the primary content tag (main > article > body)."""
        main = soup.find("main")
        if main:
            return main
        article = soup.find("article")
        if article:
            return article
        # Fallback: body minus nav/header/footer
        body = soup.find("body")
        if body:
            return body
        return soup  # type: ignore[return-value]

    def _remove_boilerplate(self, area: Tag) -> None:
        """Remove non-content tags in-place."""
        # Remove script, style, etc.
        for tag_name in _BOILERPLATE_TAGS:
            for tag in area.find_all(tag_name):
                tag.decompose()

        # Remove nav/header/footer inside body fallback
        for tag_name in _NAV_TAGS:
            for tag in area.find_all(tag_name):
                tag.decompose()

        # Remove cookie banners by class
        for el in area.find_all(True):
            classes = el.get("class", [])
            class_str = " ".join(classes).lower()
            if any(pat in class_str for pat in _COOKIE_BANNER_CLASSES):
                el.decompose()

        # Remove hidden elements
        for el in area.find_all(attrs={"aria-hidden": "true"}):
            el.decompose()

    def _extract_content_blocks(self, area: Tag) -> list[ContentBlock]:
        """Extract structured content blocks (paragraphs, lists, tables)."""
        blocks: list[ContentBlock] = []
        current_heading: Optional[str] = None

        for child in area.descendants:
            if not isinstance(child, Tag):
                continue

            tag_name = child.name
            if not tag_name:
                continue

            # Update heading context
            if tag_name in ("h1", "h2", "h3", "h4", "h5", "h6"):
                text = child.get_text(strip=True)
                if text:
                    current_heading = text
                    blocks.append(ContentBlock(
                        block_type="heading",
                        heading_context=current_heading,
                        content=text,
                    ))
                continue

            # Paragraphs
            if tag_name == "p":
                text = child.get_text(separator=" ", strip=True)
                if text and len(text) > 10:
                    blocks.append(ContentBlock(
                        block_type="paragraph",
                        heading_context=current_heading,
                        content=text,
                    ))
                continue

            # Lists (only top-level ul/ol, not nested)
            if tag_name in ("ul", "ol") and child.parent and child.parent.name not in ("ul", "ol"):
                items = [li.get_text(separator=" ", strip=True) for li in child.find_all("li")]
                items = [i for i in items if i]
                if items:
                    blocks.append(ContentBlock(
                        block_type="list",
                        heading_context=current_heading,
                        content="\n".join(f"• {item}" for item in items),
                    ))
                continue

            # Tables
            if tag_name == "table":
                rows: list[str] = []
                for row in child.find_all("tr"):
                    cells = [td.get_text(separator=" ", strip=True) for td in row.find_all(["td", "th"])]
                    if cells:
                        rows.append(" | ".join(cells))
                if rows:
                    blocks.append(ContentBlock(
                        block_type="table",
                        heading_context=current_heading,
                        content="\n".join(rows),
                    ))
                continue

        return blocks

    def _extract_text(self, area: Tag) -> str:
        """Extract and clean plain text from the content area."""
        text = area.get_text(separator="\n", strip=True)

        # Normalise whitespace
        lines = [_WS_RE.sub(" ", line).strip() for line in text.splitlines()]
        # Deduplicate consecutive identical lines (nav repetition)
        deduped: list[str] = []
        prev = None
        for line in lines:
            if line and line != prev:
                deduped.append(line)
                prev = line

        text = "\n".join(deduped)
        text = _MULTI_NL_RE.sub("\n\n", text)
        return text.strip()

    def _extract_internal_links(
        self, soup: BeautifulSoup, base_url: str
    ) -> list[str]:
        """Return normalised in-scope internal link URLs."""
        seen: set[str] = set()
        result: list[str] = []

        for tag in soup.find_all("a", href=True):
            href = tag.get("href", "").strip()
            if not href or href.startswith(("#", "mailto:", "tel:", "javascript:")):
                continue
            resolved = urljoin(base_url, href)
            normed = normalize_url(resolved)
            if normed and normed not in seen:
                seen.add(normed)
                if is_in_scope(normed, self.approved_origin, self.approved_prefix, self.extra_allowed_paths):
                    result.append(normed)

        return result
