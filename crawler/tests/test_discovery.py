"""
crawler/tests/test_discovery.py
===============================
Unit tests for URL discovery, queue management, sitemap parsing, and depth/page bounds.
"""
from pathlib import Path
import pytest
from crawler.discovery import DiscoveryQueue, parse_sitemap_xml, parse_sitemap_index

ORIGIN = "eurekasolutions.in"
PREFIX = "/Eureka2026/"
FIXTURES_DIR = Path(__file__).parent / "fixtures"


class TestSitemapParsing:
    def test_parse_standard_sitemap_fixture(self):
        sitemap_path = FIXTURES_DIR / "sitemap.xml"
        xml_text = sitemap_path.read_text(encoding="utf-8")
        urls = parse_sitemap_xml(xml_text)
        assert len(urls) == 10
        assert "https://eurekasolutions.in/services" in urls
        assert "https://eurekasolutions.in/contact-us" in urls

    def test_parse_sitemap_index(self):
        index_xml = """<?xml version="1.0" encoding="UTF-8"?>
        <sitemapindex xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">
            <sitemap><loc>https://eurekasolutions.in/sitemap1.xml</loc></sitemap>
            <sitemap><loc>https://eurekasolutions.in/sitemap2.xml</loc></sitemap>
        </sitemapindex>"""
        urls = parse_sitemap_index(index_xml)
        assert len(urls) == 2
        assert urls[0] == "https://eurekasolutions.in/sitemap1.xml"
        assert urls[1] == "https://eurekasolutions.in/sitemap2.xml"

    def test_parse_empty_or_malformed_sitemap(self):
        assert parse_sitemap_xml("<invalid>") == []
        assert parse_sitemap_xml("") == []


class TestDiscoveryQueue:
    def test_seed_enqueuing(self):
        q = DiscoveryQueue(approved_origin=ORIGIN, approved_prefix=PREFIX, max_depth=5, max_pages=10)
        q.seed("https://eurekasolutions.in/Eureka2026/")
        assert len(q) == 1
        item = q.pop()
        assert item is not None
        assert item.url == "https://eurekasolutions.in/Eureka2026/"
        assert item.depth == 0
        assert item.source == "seed"

    def test_sitemap_urls_prefixed_and_enqueued(self):
        q = DiscoveryQueue(approved_origin=ORIGIN, approved_prefix=PREFIX, max_depth=5, max_pages=20)
        sitemap_path = FIXTURES_DIR / "sitemap.xml"
        urls = parse_sitemap_xml(sitemap_path.read_text(encoding="utf-8"))
        added = q.add_from_sitemap(urls)
        assert added > 0
        first = q.pop()
        assert first is not None
        assert first.url.startswith("https://eurekasolutions.in/Eureka2026/")
        assert first.source == "sitemap"

    def test_duplicate_urls_prevented(self):
        q = DiscoveryQueue(approved_origin=ORIGIN, approved_prefix=PREFIX)
        q.seed("https://eurekasolutions.in/Eureka2026/services")
        # Try to add the same URL from a link
        added = q.add_from_page_links(["https://eurekasolutions.in/Eureka2026/services"], parent_depth=0)
        assert added == 0
        assert len(q) == 1

    def test_out_of_scope_urls_skipped(self):
        q = DiscoveryQueue(approved_origin=ORIGIN, approved_prefix=PREFIX)
        added = q.add_from_page_links(
            [
                "https://otherdomain.com/Eureka2026/test",
                "https://eurekasolutions.in/unapproved-prefix/page",
            ],
            parent_depth=0,
        )
        assert added == 0
        assert len(q) == 0
        skipped = q.skipped
        assert len(skipped) == 2
        assert all(s.skip_reason == "out_of_scope" for s in skipped)

    def test_traps_skipped(self):
        q = DiscoveryQueue(approved_origin=ORIGIN, approved_prefix=PREFIX)
        added = q.add_from_page_links(["https://eurekasolutions.in/Eureka2026/archive?page=9999"], parent_depth=0)
        assert added == 0
        assert len(q.skipped) == 1
        assert "trap" in q.skipped[0].skip_reason

    def test_max_depth_enforced(self):
        q = DiscoveryQueue(approved_origin=ORIGIN, approved_prefix=PREFIX, max_depth=2)
        # Depth 1 -> allowed
        q.add_from_page_links(["https://eurekasolutions.in/Eureka2026/d1"], parent_depth=0)
        assert len(q) == 1
        # Depth 3 -> exceeds max_depth of 2
        q.add_from_page_links(["https://eurekasolutions.in/Eureka2026/d3"], parent_depth=2)
        assert len(q) == 1
        assert any("depth_exceeded" in s.skip_reason for s in q.skipped)

    def test_max_pages_enforced(self):
        q = DiscoveryQueue(approved_origin=ORIGIN, approved_prefix=PREFIX, max_pages=3)
        links = [
            f"https://eurekasolutions.in/Eureka2026/p{i}" for i in range(10)
        ]
        q.add_from_page_links(links, parent_depth=0)
        assert q.enqueued_count == 3
        assert len(q) == 3
        assert any(s.skip_reason == "page_limit_reached" for s in q.skipped)
