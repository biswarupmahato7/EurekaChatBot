"""
crawler/tests/test_url_utils.py
===============================
Unit tests for URL normalisation, scope enforcement, SSRF protections,
trap detection, and link extraction.
"""
import pytest
from bs4 import BeautifulSoup
from crawler.url_utils import (
    add_eureka2026_prefix,
    extract_host,
    extract_internal_links,
    is_in_scope,
    is_safe_host,
    is_sitemap_url,
    is_trap_url,
    normalize_url,
    process_sitemap_url,
)

ORIGIN = "eurekasolutions.in"
PREFIX = "/Eureka2026/"


class TestNormalizeUrl:
    def test_strip_whitespace(self):
        url = "   https://eurekasolutions.in/Eureka2026/about   "
        assert normalize_url(url) == "https://eurekasolutions.in/Eureka2026/about"

    def test_empty_and_hash_only_returns_none(self):
        assert normalize_url("") is None
        assert normalize_url("   ") is None
        assert normalize_url("#heading") is None

    def test_relative_url_resolution(self):
        base = "https://eurekasolutions.in/Eureka2026/"
        assert normalize_url("about-us", base_url=base) == "https://eurekasolutions.in/Eureka2026/about-us"
        assert normalize_url("/Eureka2026/services", base_url=base) == "https://eurekasolutions.in/Eureka2026/services"
        assert normalize_url("../contact", base_url="https://eurekasolutions.in/Eureka2026/sub/") == "https://eurekasolutions.in/Eureka2026/contact"

    def test_protocol_relative_url(self):
        assert normalize_url("//eurekasolutions.in/Eureka2026/page") == "https://eurekasolutions.in/Eureka2026/page"

    def test_blocks_disallowed_schemes(self):
        for bad in ["mailto:info@eureka.com", "tel:+1234567890", "javascript:void(0)", "data:text/html,hi", "ftp://files.com"]:
            assert normalize_url(bad) is None

    def test_lowercases_host_and_scheme(self):
        url = "HTTPS://EUREKASOLUTIONS.IN/Eureka2026/Services"
        assert normalize_url(url) == "https://eurekasolutions.in/Eureka2026/Services"

    def test_strip_default_ports(self):
        assert normalize_url("http://eurekasolutions.in:80/Eureka2026/") == "http://eurekasolutions.in/Eureka2026/"
        assert normalize_url("https://eurekasolutions.in:443/Eureka2026/") == "https://eurekasolutions.in/Eureka2026/"
        # Non-default port is preserved
        assert normalize_url("https://eurekasolutions.in:8443/Eureka2026/") == "https://eurekasolutions.in:8443/Eureka2026/"

    def test_strips_fragments(self):
        url = "https://eurekasolutions.in/Eureka2026/services#overview"
        assert normalize_url(url) == "https://eurekasolutions.in/Eureka2026/services"

    def test_strips_tracking_query_params(self):
        url = "https://eurekasolutions.in/Eureka2026/services?utm_source=google&utm_medium=cpc&gclid=123&keep=1"
        cleaned = normalize_url(url)
        assert cleaned == "https://eurekasolutions.in/Eureka2026/services?keep=1"

    def test_strips_all_tracking_params_leaves_no_query(self):
        url = "https://eurekasolutions.in/Eureka2026/services?utm_source=twitter&fbclid=abc"
        assert normalize_url(url) == "https://eurekasolutions.in/Eureka2026/services"

    def test_collapses_multiple_slashes_in_path(self):
        url = "https://eurekasolutions.in//Eureka2026///services"
        assert normalize_url(url) == "https://eurekasolutions.in/Eureka2026/services"

    def test_blocks_static_asset_extensions(self):
        assert normalize_url("https://eurekasolutions.in/Eureka2026/doc.pdf") is None
        assert normalize_url("https://eurekasolutions.in/Eureka2026/archive.zip") is None
        assert normalize_url("https://eurekasolutions.in/Eureka2026/image.png") is None
        assert normalize_url("https://eurekasolutions.in/Eureka2026/style.css") is None

    def test_allows_sitemap_xml(self):
        sitemap_url = "https://eurekasolutions.in/Eureka2026/sitemap.xml"
        assert normalize_url(sitemap_url) == sitemap_url


class TestScopeEnforcement:
    def test_in_scope_exact_prefix(self):
        assert is_in_scope("https://eurekasolutions.in/Eureka2026/about", ORIGIN, PREFIX) is True
        assert is_in_scope("https://eurekasolutions.in/Eureka2026/", ORIGIN, PREFIX) is True

    def test_out_of_scope_different_host(self):
        assert is_in_scope("https://google.com/Eureka2026/", ORIGIN, PREFIX) is False
        assert is_in_scope("https://subdomain.eurekasolutions.in/Eureka2026/", ORIGIN, PREFIX) is False

    def test_out_of_scope_wrong_prefix(self):
        assert is_in_scope("https://eurekasolutions.in/other-path", ORIGIN, PREFIX) is False
        assert is_in_scope("https://eurekasolutions.in/", ORIGIN, PREFIX) is False

    def test_extra_allowed_paths(self):
        extra = ["/custom-hub/"]
        assert is_in_scope("https://eurekasolutions.in/custom-hub/page", ORIGIN, PREFIX, extra_allowed_paths=extra) is True
        assert is_in_scope("https://eurekasolutions.in/not-allowed", ORIGIN, PREFIX, extra_allowed_paths=extra) is False

    def test_host_with_port_in_scope(self):
        assert is_in_scope("https://eurekasolutions.in:443/Eureka2026/services", ORIGIN, PREFIX) is True


class TestSitemapHelpers:
    def test_is_sitemap_url(self):
        assert is_sitemap_url("https://eurekasolutions.in/Eureka2026/sitemap.xml") is True
        assert is_sitemap_url("https://eurekasolutions.in/sitemap_index.xml") is True
        assert is_sitemap_url("https://eurekasolutions.in/Eureka2026/services") is False

    def test_add_eureka2026_prefix(self):
        assert add_eureka2026_prefix("https://eurekasolutions.in/services") == "https://eurekasolutions.in/Eureka2026/services"
        assert add_eureka2026_prefix("https://eurekasolutions.in/") == "https://eurekasolutions.in/Eureka2026/"
        # If already prefixed, leaves untouched
        assert add_eureka2026_prefix("https://eurekasolutions.in/Eureka2026/services") == "https://eurekasolutions.in/Eureka2026/services"

    def test_process_sitemap_url(self):
        res = process_sitemap_url("https://eurekasolutions.in/services", ORIGIN, PREFIX)
        assert res == "https://eurekasolutions.in/Eureka2026/services"
        res_already = process_sitemap_url("https://eurekasolutions.in/Eureka2026/about", ORIGIN, PREFIX)
        assert res_already == "https://eurekasolutions.in/Eureka2026/about"
        assert process_sitemap_url("https://external.com/services", ORIGIN, PREFIX) is None


class TestSSRFProtection:
    def test_blocks_metadata_hosts(self):
        safe, reason = is_safe_host("169.254.169.254")
        assert not safe
        assert "metadata" in reason.lower() or "private" in reason.lower()

        safe, _ = is_safe_host("metadata.google.internal")
        assert not safe

    def test_blocks_private_and_loopback_ips(self):
        for ip in ["127.0.0.1", "10.0.0.1", "192.168.1.1", "172.16.0.5", "::1"]:
            safe, _ = is_safe_host(ip)
            assert not safe, f"{ip} should be rejected"

    def test_allows_public_hosts(self, monkeypatch):
        # Public IP directly
        safe, reason = is_safe_host("8.8.8.8")
        assert safe, reason
        assert reason == ""

        # Mock socket.getaddrinfo to test domain resolution safely offline
        import socket
        def fake_getaddrinfo(host, port):
            return [(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("93.184.216.34", 0))]

        monkeypatch.setattr(socket, "getaddrinfo", fake_getaddrinfo)
        safe, reason = is_safe_host("eurekasolutions.in")
        assert safe, reason

    def test_extract_host(self):
        assert extract_host("https://eurekasolutions.in/Eureka2026/services") == "eurekasolutions.in"
        assert extract_host("https://eurekasolutions.in:8080/Eureka2026/") == "eurekasolutions.in"
        assert extract_host("invalid-url") is None


class TestTrapDetection:
    def test_calendar_traps(self):
        is_trap, _ = is_trap_url("https://eurekasolutions.in/Eureka2026/2023/04/15/event")
        assert is_trap

    def test_deep_pagination_traps(self):
        is_trap, _ = is_trap_url("https://eurekasolutions.in/Eureka2026/news?page=999")
        assert is_trap
        is_trap2, _ = is_trap_url("https://eurekasolutions.in/Eureka2026/news?page=2")
        assert not is_trap2

    def test_session_id_traps(self):
        is_trap, _ = is_trap_url("https://eurekasolutions.in/Eureka2026/view?session=abcdef1234567890abcdef1234567890")
        assert is_trap


class TestInternalLinkExtraction:
    def test_extracts_and_deduplicates_links(self):
        html = """
        <html><body>
            <a href="/Eureka2026/about">About</a>
            <a href="https://eurekasolutions.in/Eureka2026/about#team">About Team</a>
            <a href="/Eureka2026/services">Services</a>
            <a href="https://external.com/page">External</a>
            <a href="/Eureka2026/news?page=500">Pagination Trap</a>
            <a href="mailto:contact@eureka.com">Email</a>
        </body></html>
        """
        soup = BeautifulSoup(html, "html.parser")
        links = extract_internal_links(
            soup,
            base_url="https://eurekasolutions.in/Eureka2026/",
            approved_origin=ORIGIN,
            approved_prefix=PREFIX,
        )
        assert "https://eurekasolutions.in/Eureka2026/about" in links
        assert "https://eurekasolutions.in/Eureka2026/services" in links
        # External, trap, mailto, and fragment dupes excluded
        assert len(links) == 2
