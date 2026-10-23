"""
crawler/fetcher.py
==================
Safe HTTP fetcher with robots.txt respect, retries, SSRF protection,
configurable timeouts, and response size limits.

Fetch results are structured FetchStatus objects — never raw exceptions.
One failed URL must not crash the crawl.
"""
from __future__ import annotations

import logging
import time
import urllib.robotparser
from typing import Optional
from urllib.parse import urlparse

import requests
from requests.exceptions import (
    ConnectionError as ReqConnectionError,
    ReadTimeout,
    RequestException,
    TooManyRedirects,
)

from crawler.models import FetchStatus
from crawler.url_utils import extract_host, is_in_scope, is_safe_host, normalize_url

logger = logging.getLogger(__name__)

# Statuses that are definitely not retryable
_NON_RETRYABLE_STATUSES: frozenset[int] = frozenset({
    400, 401, 403, 404, 405, 410, 451,
})
# Statuses that indicate rate-limiting or server errors (retryable with backoff)
_RETRYABLE_STATUSES: frozenset[int] = frozenset({
    429, 500, 502, 503, 504,
})


class RobotsTxtCache:
    """Per-origin robots.txt cache. Fetches once per origin, then caches."""

    def __init__(self, user_agent: str, timeout: int = 10) -> None:
        self._user_agent = user_agent
        self._timeout = timeout
        self._cache: dict[str, urllib.robotparser.RobotFileParser | None] = {}

    def _origin_key(self, url: str) -> str:
        parsed = urlparse(url)
        return f"{parsed.scheme}://{parsed.netloc}"

    def _fetch_robots(self, origin: str) -> urllib.robotparser.RobotFileParser | None:
        robots_url = f"{origin}/robots.txt"
        parser = urllib.robotparser.RobotFileParser()
        parser.set_url(robots_url)
        try:
            parser.read()
            logger.debug("Fetched robots.txt from %s", robots_url)
            return parser
        except Exception as exc:
            # A missing/inaccessible robots.txt means no restrictions
            logger.debug("No robots.txt at %s (%s) — treating as unrestricted", robots_url, exc)
            return None

    def is_allowed(self, url: str) -> bool:
        """Return True if robots.txt permits fetching url."""
        origin = self._origin_key(url)
        if origin not in self._cache:
            self._cache[origin] = self._fetch_robots(origin)

        parser = self._cache[origin]
        if parser is None:
            return True  # No robots.txt = no restrictions

        allowed = parser.can_fetch(self._user_agent, url)
        if not allowed:
            logger.info("robots.txt disallows: %s", url)
        return allowed


class SafeFetcher:
    """HTTP fetcher with safety controls.

    Parameters
    ----------
    user_agent : descriptive User-Agent string
    timeout_seconds : per-request timeout
    max_retries : number of retry attempts on transient errors
    delay_seconds : base delay between requests (and between retries)
    max_response_bytes : maximum acceptable response body size
    approved_origin : for redirect scope checks
    approved_prefix : for redirect scope checks
    """

    def __init__(
        self,
        user_agent: str,
        timeout_seconds: int = 20,
        max_retries: int = 3,
        delay_seconds: float = 1.5,
        max_response_bytes: int = 5_242_880,
        approved_origin: str = "eurekasolutions.in",
        approved_prefix: str = "/Eureka2026/",
        extra_allowed_paths: list[str] | None = None,
        robots_cache: RobotsTxtCache | None = None,
    ) -> None:
        self.user_agent = user_agent
        self.timeout_seconds = timeout_seconds
        self.max_retries = max_retries
        self.delay_seconds = delay_seconds
        self.max_response_bytes = max_response_bytes
        self.approved_origin = approved_origin
        self.approved_prefix = approved_prefix
        self.extra_allowed_paths = extra_allowed_paths or []

        self._session = requests.Session()
        self._session.headers.update({"User-Agent": user_agent})

        self._robots = robots_cache or RobotsTxtCache(user_agent)

    # ── Public API ────────────────────────────────────────────────────────────

    def fetch(self, url: str, allow_redirects: bool = True) -> FetchStatus:
        """Fetch url safely and return a structured FetchStatus.

        Never raises. All errors are captured in FetchStatus.
        """
        # SSRF check on initial URL
        host = extract_host(url)
        if host:
            safe, reason = is_safe_host(host)
            if not safe:
                logger.warning("SSRF block on %s: %s", url, reason)
                return FetchStatus(
                    url=url, final_url=url,
                    blocked=True, block_reason=f"SSRF:{reason}",
                )

        # robots.txt check
        if not self._robots.is_allowed(url):
            return FetchStatus(
                url=url, final_url=url,
                robots_disallowed=True, skipped=True,
                skip_reason="robots_disallowed",
            )

        result = self._fetch_with_retry(url, allow_redirects=allow_redirects)
        return result

    def fetch_text(self, url: str, content_types: tuple[str, ...] = ("text/html", "text/xml", "application/xml")) -> tuple[FetchStatus, str]:
        """Fetch and return (FetchStatus, text). Text is empty on failure."""
        status = self.fetch(url)
        if status.blocked or status.skipped or status.error or status.http_status not in (200,):
            return status, ""
        # Validate content type
        ct = (status.content_type or "").lower()
        if not any(t in ct for t in content_types):
            status.error = f"unexpected content-type: {status.content_type!r}"
            return status, ""
        # The response text was stored during fetch
        return status, getattr(status, "_body_text", "")

    # ── Internal ─────────────────────────────────────────────────────────────

    def _fetch_with_retry(self, url: str, allow_redirects: bool = True) -> FetchStatus:
        attempt = 0
        last_status: Optional[int] = None
        was_retried = False

        while attempt <= self.max_retries:
            if attempt > 0:
                backoff = self.delay_seconds * (2 ** (attempt - 1))
                logger.debug("Retry %d for %s (backoff %.1fs)", attempt, url, backoff)
                time.sleep(backoff)
                was_retried = True

            try:
                response = self._session.get(
                    url,
                    timeout=self.timeout_seconds,
                    allow_redirects=False,  # We handle redirects manually
                    stream=True,
                )

                # Manual redirect handling with SSRF revalidation
                redirect_count = 0
                final_url = url
                while response.is_redirect and redirect_count < 10:
                    location = response.headers.get("Location", "")
                    if not location:
                        break
                    normed = normalize_url(location, base_url=final_url)
                    if not normed:
                        return FetchStatus(
                            url=url, final_url=final_url, http_status=response.status_code,
                            error=f"Invalid redirect location: {location!r}",
                            was_retried=was_retried, retry_count=attempt,
                        )

                    # SSRF check on redirect target
                    redir_host = extract_host(normed)
                    if redir_host:
                        safe, ssrf_reason = is_safe_host(redir_host)
                        if not safe:
                            return FetchStatus(
                                url=url, final_url=normed,
                                blocked=True, block_reason=f"redirect_SSRF:{ssrf_reason}",
                                was_retried=was_retried, retry_count=attempt,
                            )

                    # Scope check on redirect: block out-of-scope redirect targets (CRAWL-003)
                    if not is_in_scope(normed, self.approved_origin, self.approved_prefix, self.extra_allowed_paths):
                        logger.warning("Blocked out-of-scope redirect from %s to %s", url, normed)
                        return FetchStatus(
                            url=url, final_url=normed,
                            blocked=True, block_reason=f"out_of_scope_redirect:{normed}",
                            was_retried=was_retried, retry_count=attempt,
                        )

                    final_url = normed
                    response = self._session.get(
                        normed,
                        timeout=self.timeout_seconds,
                        allow_redirects=False,
                        stream=True,
                    )
                    redirect_count += 1

                # Read body with size limit
                http_status = response.status_code
                last_status = http_status
                content_type = response.headers.get("Content-Type", "")

                # Size check
                content_length = int(response.headers.get("Content-Length", 0) or 0)
                if content_length > self.max_response_bytes:
                    response.close()
                    return FetchStatus(
                        url=url, final_url=final_url, http_status=http_status,
                        content_type=content_type,
                        error=f"Content-Length {content_length} exceeds limit {self.max_response_bytes}",
                        was_retried=was_retried, retry_count=attempt,
                    )

                chunks: list[bytes] = []
                total = 0
                for chunk in response.iter_content(chunk_size=65536):
                    total += len(chunk)
                    if total > self.max_response_bytes:
                        response.close()
                        return FetchStatus(
                            url=url, final_url=final_url, http_status=http_status,
                            content_type=content_type,
                            error=f"Response body exceeded size limit {self.max_response_bytes}",
                            was_retried=was_retried, retry_count=attempt,
                        )
                    chunks.append(chunk)

                body = b"".join(chunks)

                # Build successful result
                fs = FetchStatus(
                    url=url,
                    final_url=final_url,
                    http_status=http_status,
                    content_type=content_type,
                    response_size_bytes=len(body),
                    was_retried=was_retried,
                    retry_count=attempt,
                )

                if http_status in _NON_RETRYABLE_STATUSES:
                    fs.error = f"HTTP {http_status}"
                    return fs  # Don't retry

                if http_status in _RETRYABLE_STATUSES:
                    attempt += 1
                    continue  # Retry

                if http_status == 200:
                    # Decode body
                    encoding = response.encoding or "utf-8"
                    try:
                        text = body.decode(encoding, errors="replace")
                    except (LookupError, UnicodeDecodeError):
                        text = body.decode("utf-8", errors="replace")

                    # Store text for fetch_text() to retrieve
                    fs._body_text = text  # type: ignore[attr-defined]
                    return fs

                # Other statuses (201, 204, 301, etc.)
                fs._body_text = ""  # type: ignore[attr-defined]
                return fs

            except ReadTimeout:
                logger.warning("Timeout on attempt %d for %s", attempt + 1, url)
                attempt += 1
                if attempt > self.max_retries:
                    return FetchStatus(
                        url=url, final_url=url, http_status=last_status,
                        error=f"Timeout after {self.max_retries + 1} attempts",
                        was_retried=was_retried, retry_count=attempt - 1,
                    )

            except TooManyRedirects:
                return FetchStatus(
                    url=url, final_url=url,
                    error="Too many redirects",
                    was_retried=was_retried, retry_count=attempt,
                )

            except ReqConnectionError as exc:
                logger.warning("Connection error for %s: %s", url, exc)
                attempt += 1
                if attempt > self.max_retries:
                    return FetchStatus(
                        url=url, final_url=url, http_status=last_status,
                        error=f"Connection error: {exc}",
                        was_retried=was_retried, retry_count=attempt - 1,
                    )

            except RequestException as exc:
                return FetchStatus(
                    url=url, final_url=url,
                    error=f"Request error: {exc}",
                    was_retried=was_retried, retry_count=attempt,
                )

        return FetchStatus(
            url=url, final_url=url, http_status=last_status,
            error=f"Max retries ({self.max_retries}) exceeded",
            was_retried=True, retry_count=self.max_retries,
        )

    def add_delay(self) -> None:
        """Sleep for the configured inter-request delay."""
        if self.delay_seconds > 0:
            time.sleep(self.delay_seconds)
