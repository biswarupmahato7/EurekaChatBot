"""
crawler/discovery.py
====================
URL discovery: queue management, sitemap parsing, and link discovery.

DESIGN RULE: This module performs NO HTTP page-fetching.
It may receive raw HTML/XML already fetched by the fetcher, but does
not make GET requests itself. This keeps discovery independently testable.

A.0 findings integrated:
- Sitemap at https://eurekasolutions.in/Eureka2026/sitemap.xml (103 URLs)
- Sitemap URLs lack /Eureka2026/ prefix; url_utils.process_sitemap_url adds it
- All pages are server-rendered HTML
"""
from __future__ import annotations

import logging
from collections import deque
from typing import Generator

from bs4 import BeautifulSoup

from crawler.models import DiscoveredURL
from crawler.url_utils import (
    extract_internal_links,
    is_in_scope,
    is_trap_url,
    normalize_url,
    process_sitemap_url,
)

logger = logging.getLogger(__name__)


class DiscoveryQueue:
    """BFS URL queue with depth tracking, seen-set, and scope enforcement.

    Attributes
    ----------
    approved_origin : str
    approved_prefix : str
    max_depth : int
    max_pages : int
    extra_allowed_paths : list[str]
    """

    def __init__(
        self,
        approved_origin: str,
        approved_prefix: str,
        max_depth: int = 6,
        max_pages: int = 150,
        extra_allowed_paths: list[str] | None = None,
    ) -> None:
        self.approved_origin = approved_origin
        self.approved_prefix = approved_prefix
        self.max_depth = max_depth
        self.max_pages = max_pages
        self.extra_allowed_paths: list[str] = extra_allowed_paths or []

        self._queue: deque[DiscoveredURL] = deque()
        self._seen: set[str] = set()
        self._skipped: list[DiscoveredURL] = []
        self._enqueued_count: int = 0

    # ── Enqueue helpers ──────────────────────────────────────────────────────

    def _try_enqueue(
        self,
        raw_url: str,
        depth: int,
        source: str,
    ) -> DiscoveredURL | None:
        """Normalise, scope-check, and enqueue url. Return DiscoveredURL or None."""
        normed = normalize_url(raw_url)
        if normed is None:
            return None

        if normed in self._seen:
            return None

        # Scope check
        if not is_in_scope(normed, self.approved_origin, self.approved_prefix, self.extra_allowed_paths):
            skip = DiscoveredURL(url=raw_url, normalized_url=normed, depth=depth, source=source, skip_reason="out_of_scope")
            self._skipped.append(skip)
            self._seen.add(normed)
            return None

        # Trap check
        is_trap, trap_reason = is_trap_url(normed)
        if is_trap:
            skip = DiscoveredURL(url=raw_url, normalized_url=normed, depth=depth, source=source, skip_reason=f"trap:{trap_reason}")
            self._skipped.append(skip)
            self._seen.add(normed)
            return None

        # Depth check
        if depth > self.max_depth:
            skip = DiscoveredURL(url=raw_url, normalized_url=normed, depth=depth, source=source, skip_reason=f"depth_exceeded:{depth}")
            self._skipped.append(skip)
            self._seen.add(normed)
            return None

        # Page limit
        if self._enqueued_count >= self.max_pages:
            skip = DiscoveredURL(url=raw_url, normalized_url=normed, depth=depth, source=source, skip_reason="page_limit_reached")
            self._skipped.append(skip)
            self._seen.add(normed)
            return None

        self._seen.add(normed)
        entry = DiscoveredURL(url=raw_url, normalized_url=normed, depth=depth, source=source)
        self._queue.append(entry)
        self._enqueued_count += 1
        return entry

    def seed(self, url: str) -> None:
        """Add the seed/start URL."""
        normed = normalize_url(url) or url
        self._try_enqueue(normed, depth=0, source="seed")

    def add_from_sitemap(self, urls: list[str]) -> int:
        """Add URLs discovered from a sitemap. Returns count added."""
        added = 0
        for raw in urls:
            processed = process_sitemap_url(raw, self.approved_origin, self.approved_prefix)
            if processed and processed not in self._seen:
                entry = self._try_enqueue(processed, depth=1, source="sitemap")
                if entry:
                    added += 1
        return added

    def add_from_page_links(self, links: list[str], parent_depth: int) -> int:
        """Add in-scope links discovered on a crawled page."""
        added = 0
        for link in links:
            entry = self._try_enqueue(link, depth=parent_depth + 1, source="link")
            if entry:
                added += 1
        return added

    # ── Queue interface ──────────────────────────────────────────────────────

    def __len__(self) -> int:
        return len(self._queue)

    def __bool__(self) -> bool:
        return bool(self._queue)

    def pop(self) -> DiscoveredURL | None:
        """Return and remove the next URL to crawl, or None if empty."""
        if self._queue:
            return self._queue.popleft()
        return None

    # ── Reporting ────────────────────────────────────────────────────────────

    @property
    def seen_count(self) -> int:
        return len(self._seen)

    @property
    def skipped(self) -> list[DiscoveredURL]:
        return list(self._skipped)

    @property
    def enqueued_count(self) -> int:
        return self._enqueued_count


# ===========================================================================
# Sitemap parsing
# ===========================================================================

def parse_sitemap_xml(xml_text: str, base_url: str = "") -> list[str]:
    """Parse a sitemap XML and return raw <loc> URL strings.

    Handles both urlset (standard) and sitemapindex (sitemap-of-sitemaps).
    Does NOT perform network requests — receives already-fetched text.
    """
    try:
        soup = BeautifulSoup(xml_text, "xml")
    except Exception:
        # Fall back to html.parser for malformed XML
        soup = BeautifulSoup(xml_text, "lxml")

    urls: list[str] = []

    # Standard sitemap
    for loc in soup.find_all("loc"):
        url = loc.get_text(strip=True)
        if url:
            urls.append(url)

    return urls


def parse_sitemap_index(xml_text: str) -> list[str]:
    """Parse a sitemap index and return child sitemap URLs."""
    try:
        soup = BeautifulSoup(xml_text, "xml")
    except Exception:
        soup = BeautifulSoup(xml_text, "lxml")

    return [loc.get_text(strip=True) for loc in soup.find_all("loc") if loc.get_text(strip=True)]
