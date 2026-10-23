"""
crawler/tests/test_fetcher.py
=============================
Unit tests for SafeFetcher with mocked HTTP behavior and robots.txt caching.
Guarantees tests run completely offline with no network calls and no sleeping.
"""
from unittest.mock import MagicMock, patch
import pytest
import requests
from requests.exceptions import ReadTimeout, ConnectionError as ReqConnectionError

from crawler.fetcher import RobotsTxtCache, SafeFetcher
from crawler.models import FetchStatus


@pytest.fixture
def mock_robots():
    robots = MagicMock(spec=RobotsTxtCache)
    robots.is_allowed.return_value = True
    return robots


@pytest.fixture
def fetcher(mock_robots, monkeypatch):
    # Set delay_seconds=0 and monkeypatch time.sleep to run instantly
    monkeypatch.setattr("time.sleep", lambda s: None)
    return SafeFetcher(
        user_agent="TestBot/1.0",
        timeout_seconds=2,
        max_retries=2,
        delay_seconds=0.0,
        max_response_bytes=1000,
        approved_origin="eurekasolutions.in",
        approved_prefix="/Eureka2026/",
        robots_cache=mock_robots,
    )


class TestRobotsTxtCache:
    def test_robots_allowed_when_parser_allows(self):
        cache = RobotsTxtCache(user_agent="TestBot/1.0")
        mock_parser = MagicMock()
        mock_parser.can_fetch.return_value = True
        cache._cache["https://eurekasolutions.in"] = mock_parser

        assert cache.is_allowed("https://eurekasolutions.in/Eureka2026/services") is True

    def test_robots_disallowed(self):
        cache = RobotsTxtCache(user_agent="TestBot/1.0")
        mock_parser = MagicMock()
        mock_parser.can_fetch.return_value = False
        cache._cache["https://eurekasolutions.in"] = mock_parser

        assert cache.is_allowed("https://eurekasolutions.in/Eureka2026/private") is False

    def test_missing_robots_defaults_to_allowed(self):
        cache = RobotsTxtCache(user_agent="TestBot/1.0")
        cache._cache["https://eurekasolutions.in"] = None
        assert cache.is_allowed("https://eurekasolutions.in/Eureka2026/services") is True


class TestSafeFetcher:
    def test_ssrf_initial_url_blocked(self, fetcher):
        status = fetcher.fetch("http://127.0.0.1/admin")
        assert status.blocked is True
        assert "SSRF" in (status.block_reason or "")

        status_meta = fetcher.fetch("http://169.254.169.254/latest/meta-data/")
        assert status_meta.blocked is True

    def test_robots_disallowed_skipped(self, fetcher, mock_robots):
        mock_robots.is_allowed.return_value = False
        status = fetcher.fetch("https://eurekasolutions.in/Eureka2026/secret")
        assert status.skipped is True
        assert status.robots_disallowed is True
        assert status.skip_reason == "robots_disallowed"

    def test_successful_fetch_html(self, fetcher):
        mock_resp = MagicMock(spec=requests.Response)
        mock_resp.is_redirect = False
        mock_resp.status_code = 200
        mock_resp.headers = {"Content-Type": "text/html; charset=utf-8", "Content-Length": "24"}
        mock_resp.encoding = "utf-8"
        mock_resp.iter_content.return_value = [b"<html>Hello world</html>"]

        with patch.object(fetcher._session, "get", return_value=mock_resp):
            status, text = fetcher.fetch_text("https://eurekasolutions.in/Eureka2026/services")
            assert status.http_status == 200
            assert "Hello world" in text
            assert status.response_size_bytes == 24
            assert status.was_retried is False

    def test_non_retryable_404(self, fetcher):
        mock_resp = MagicMock(spec=requests.Response)
        mock_resp.is_redirect = False
        mock_resp.status_code = 404
        mock_resp.headers = {"Content-Type": "text/html"}
        mock_resp.iter_content.return_value = [b"Not Found"]

        with patch.object(fetcher._session, "get", return_value=mock_resp) as mock_get:
            status = fetcher.fetch("https://eurekasolutions.in/Eureka2026/nonexistent")
            assert status.http_status == 404
            assert status.error == "HTTP 404"
            assert mock_get.call_count == 1  # No retries for 404

    def test_retryable_500_retries_and_exhausts(self, fetcher):
        mock_resp = MagicMock(spec=requests.Response)
        mock_resp.is_redirect = False
        mock_resp.status_code = 500
        mock_resp.headers = {"Content-Type": "text/html"}
        mock_resp.iter_content.return_value = [b"Server Error"]

        with patch.object(fetcher._session, "get", return_value=mock_resp) as mock_get:
            status = fetcher.fetch("https://eurekasolutions.in/Eureka2026/error")
            assert status.http_status == 500
            # initial attempt + 2 retries = 3 calls
            assert mock_get.call_count == 3
            assert status.was_retried is True

    def test_timeout_retries_and_captures_error(self, fetcher):
        with patch.object(fetcher._session, "get", side_effect=ReadTimeout("timed out")) as mock_get:
            status = fetcher.fetch("https://eurekasolutions.in/Eureka2026/slow")
            assert "Timeout" in (status.error or "")
            assert mock_get.call_count == 3

    def test_content_length_exceeded_rejected(self, fetcher):
        mock_resp = MagicMock(spec=requests.Response)
        mock_resp.is_redirect = False
        mock_resp.status_code = 200
        mock_resp.headers = {"Content-Length": "9999999", "Content-Type": "text/html"}

        with patch.object(fetcher._session, "get", return_value=mock_resp):
            status = fetcher.fetch("https://eurekasolutions.in/Eureka2026/huge")
            assert status.error is not None
            assert "exceeds limit" in status.error

    def test_stream_body_size_exceeded(self, fetcher):
        mock_resp = MagicMock(spec=requests.Response)
        mock_resp.is_redirect = False
        mock_resp.status_code = 200
        mock_resp.headers = {"Content-Type": "text/html"}
        # Emit chunks totaling > 1000 bytes
        mock_resp.iter_content.return_value = [b"x" * 600, b"x" * 600]

        with patch.object(fetcher._session, "get", return_value=mock_resp):
            status = fetcher.fetch("https://eurekasolutions.in/Eureka2026/huge_stream")
            assert status.error is not None
            assert "exceeded size limit" in status.error

    def test_redirect_to_ssrf_target_blocked(self, fetcher):
        resp1 = MagicMock(spec=requests.Response)
        resp1.is_redirect = True
        resp1.status_code = 302
        resp1.headers = {"Location": "http://127.0.0.1/admin"}

        with patch.object(fetcher._session, "get", return_value=resp1):
            status = fetcher.fetch("https://eurekasolutions.in/Eureka2026/redir")
            assert status.blocked is True
            assert "redirect_SSRF" in (status.block_reason or "")

    def test_redirect_out_of_scope_blocked(self, fetcher):
        resp1 = MagicMock(spec=requests.Response)
        resp1.is_redirect = True
        resp1.status_code = 302
        resp1.headers = {"Location": "https://malicious-external-site.com/phishing"}

        with patch.object(fetcher._session, "get", return_value=resp1):
            status = fetcher.fetch("https://eurekasolutions.in/Eureka2026/out_redir")
            assert status.blocked is True
            assert "out_of_scope_redirect" in (status.block_reason or "")

