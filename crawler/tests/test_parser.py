"""
crawler/tests/test_parser.py
============================
Unit tests for HTML parsing, content cleaning, metadata extraction,
and Unicode preservation using local HTML fixtures.
"""
from pathlib import Path
import pytest
from crawler.parser import PageParser

FIXTURES_DIR = Path(__file__).parent / "fixtures"


@pytest.fixture
def parser():
    return PageParser(
        approved_origin="eurekasolutions.in",
        approved_prefix="/Eureka2026/",
    )


class TestPageParserWithFixtures:
    def test_services_page_fixture(self, parser):
        html = (FIXTURES_DIR / "services_page.html").read_text(encoding="utf-8")
        record = parser.parse(
            html_text=html,
            source_url="https://eurekasolutions.in/Eureka2026/services",
            final_url="https://eurekasolutions.in/Eureka2026/services",
            http_status=200,
        )

        assert record.title == "Technology Services | Eureka Solutions"
        assert record.meta_description is not None
        assert "enterprise software" in record.meta_description.lower()
        assert record.canonical_url == "https://eurekasolutions.in/services"

        # Headings
        h_texts = [h.text for h in record.headings]
        assert "Technology Services" in h_texts
        assert "Enterprise Software" in h_texts
        assert "AI & Intelligent Automation" in h_texts

        # Boilerplate removal: nav and footer should not appear in main text
        assert "Privacy Policy" not in record.content
        assert "All rights reserved" not in record.content
        assert "Technology Services" in record.content
        assert "Enterprise ERP Solutions" in record.content

        # Content blocks
        assert len(record.content_blocks) > 0
        block_types = {b.block_type for b in record.content_blocks}
        assert "paragraph" in block_types or "heading" in block_types or "list" in block_types

        # Internal links
        assert "https://eurekasolutions.in/Eureka2026/about-us" in record.internal_links
        assert "https://eurekasolutions.in/Eureka2026/contact-us" in record.internal_links

        # Hashes
        assert len(record.page_id) == 64
        assert len(record.content_hash) == 64
        assert not record.is_empty
        assert not record.is_low_content

    def test_no_main_page_fallback(self, parser):
        html = (FIXTURES_DIR / "no_main_page.html").read_text(encoding="utf-8")
        record = parser.parse(
            html_text=html,
            source_url="https://eurekasolutions.in/Eureka2026/fallback",
            final_url="https://eurekasolutions.in/Eureka2026/fallback",
            http_status=200,
        )

        assert record.title == "No Main Tag Page"
        assert "Fallback Content" in record.content
        assert "enterprise software solutions" in record.content
        # Warning about fallback to body
        assert any("fallback" in w.lower() or "no <main>" in w.lower() for w in record.warnings)

    def test_empty_page_fixture(self, parser):
        html = (FIXTURES_DIR / "empty_page.html").read_text(encoding="utf-8")
        record = parser.parse(
            html_text=html,
            source_url="https://eurekasolutions.in/Eureka2026/empty",
            final_url="https://eurekasolutions.in/Eureka2026/empty",
            http_status=200,
        )

        assert record.is_empty or record.is_low_content
        assert any("low content" in w.lower() or "empty" in w.lower() for w in record.warnings)

    def test_unicode_page_fixture(self, parser):
        html = (FIXTURES_DIR / "unicode_page.html").read_text(encoding="utf-8")
        record = parser.parse(
            html_text=html,
            source_url="https://eurekasolutions.in/Eureka2026/unicode",
            final_url="https://eurekasolutions.in/Eureka2026/unicode",
            http_status=200,
        )

        assert "企業技術ソリューション" in record.content
        assert "عميلنا" in record.content
        assert "हमारे ग्राहक" in record.content
        assert "我们的客户" in record.content
        assert "€" in record.content
        assert "₹" in record.content

    def test_table_parsing(self, parser):
        html = """
        <html><body><main>
          <h1>Pricing Table</h1>
          <table>
            <thead><tr><th>Plan</th><th>Price</th></tr></thead>
            <tbody>
              <tr><td>Starter</td><td>$100</td></tr>
              <tr><td>Enterprise</td><td>Custom</td></tr>
            </tbody>
          </table>
        </main></body></html>
        """
        record = parser.parse(
            html_text=html,
            source_url="https://eurekasolutions.in/Eureka2026/pricing",
            final_url="https://eurekasolutions.in/Eureka2026/pricing",
        )
        assert "Starter" in record.content
        assert "Enterprise" in record.content
        table_blocks = [b for b in record.content_blocks if b.block_type == "table"]
        assert len(table_blocks) == 1

    def test_deterministic_output(self, parser):
        html = (FIXTURES_DIR / "services_page.html").read_text(encoding="utf-8")
        rec1 = parser.parse(html, "https://eurekasolutions.in/Eureka2026/services", "https://eurekasolutions.in/Eureka2026/services")
        rec2 = parser.parse(html, "https://eurekasolutions.in/Eureka2026/services", "https://eurekasolutions.in/Eureka2026/services")
        assert rec1.page_id == rec2.page_id
        assert rec1.content_hash == rec2.content_hash
        assert rec1.content == rec2.content
