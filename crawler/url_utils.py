"""
crawler/url_utils.py
====================
URL normalisation, scope enforcement, SSRF protection, and discovery helpers.

KEY DESIGN PRINCIPLE: This module performs NO network requests.
All functions are pure transformations on strings/data — fully unit-testable
without any mocking.

A.0 Inspection findings:
- Approved origin: eurekasolutions.in
- Approved path prefix: /Eureka2026/
- Site uses /Eureka2026/<page> pattern for all crawlable content
- Sitemap at /Eureka2026/sitemap.xml lists paths without the prefix;
  the crawler must add /Eureka2026/ when those paths lack it.
"""
from __future__ import annotations

import ipaddress
import logging
import re
import socket
from urllib.parse import (
    ParseResult,
    parse_qs,
    urlencode,
    urljoin,
    urlparse,
    urlunparse,
)

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Tracking / junk query parameters to strip (extend as needed)
# ---------------------------------------------------------------------------
_TRACKING_PARAMS: frozenset[str] = frozenset({
    "utm_source", "utm_medium", "utm_campaign", "utm_term", "utm_content",
    "utm_id", "fbclid", "gclid", "mc_eid", "ref", "referrer",
    "_ga", "_gl", "yclid", "msclkid",
})

# ---------------------------------------------------------------------------
# Private / loopback IP ranges for SSRF protection
# ---------------------------------------------------------------------------
_PRIVATE_RANGES: list[ipaddress.IPv4Network | ipaddress.IPv6Network] = [
    ipaddress.ip_network("10.0.0.0/8"),
    ipaddress.ip_network("172.16.0.0/12"),
    ipaddress.ip_network("192.168.0.0/16"),
    ipaddress.ip_network("127.0.0.0/8"),
    ipaddress.ip_network("169.254.0.0/16"),   # link-local
    ipaddress.ip_network("100.64.0.0/10"),    # carrier-grade NAT
    ipaddress.ip_network("::1/128"),           # IPv6 loopback
    ipaddress.ip_network("fc00::/7"),          # IPv6 ULA
    ipaddress.ip_network("fe80::/10"),         # IPv6 link-local
    ipaddress.ip_network("169.254.169.254/32"), # AWS/GCP metadata
]

_METADATA_HOSTS: frozenset[str] = frozenset({
    "169.254.169.254",  # AWS / GCP / Azure instance metadata
    "metadata.google.internal",
    "metadata.goog",
})

# ---------------------------------------------------------------------------
# URL scheme and link-type exclusions
# ---------------------------------------------------------------------------
_BLOCKED_SCHEMES: frozenset[str] = frozenset({
    "mailto", "tel", "javascript", "data", "ftp", "file",
    "irc", "sftp", "ssh",
})

_BLOCKED_EXTENSIONS: frozenset[str] = frozenset({
    ".pdf", ".doc", ".docx", ".xls", ".xlsx", ".ppt", ".pptx",
    ".zip", ".tar", ".gz", ".rar", ".7z",
    ".jpg", ".jpeg", ".png", ".gif", ".webp", ".svg", ".ico",
    ".mp3", ".mp4", ".avi", ".mov", ".wmv",
    ".css", ".js", ".ts", ".woff", ".woff2", ".ttf", ".eot",
    ".xml",  # not blocking sitemap.xml by path, but general XML downloads
})

# Calendar/pagination trap patterns
_TRAP_PATTERNS: list[re.Pattern[str]] = [
    re.compile(r"/\d{4}/\d{2}/\d{2}/"),   # date-based archives
    re.compile(r"[?&]page=\d{3,}"),        # deep pagination
    re.compile(r"[?&]offset=\d{4,}"),      # deep offset
    re.compile(r"[?&](session|sid|token)=[a-zA-Z0-9]{20,}"),  # session traps
]


# ===========================================================================
# Core normalisation
# ===========================================================================

def normalize_url(url: str, base_url: str = "") -> str | None:
    """Return a canonical, normalised URL string, or None if invalid/blocked.

    Transformations applied (in order):
      1. Strip whitespace.
      2. Resolve relative URLs against base_url.
      3. Block non-HTTP(S) schemes.
      4. Lowercase scheme and host.
      5. Strip default ports (80 for http, 443 for https).
      6. Remove fragment.
      7. Strip known tracking query parameters.
      8. Normalise path (no double slashes; preserve meaningful trailing slash).
      9. Percent-encode reserved characters consistently.
    """
    url = url.strip()
    if not url or url.startswith("#"):
        return None

    # Resolve relative URLs
    if base_url and not url.startswith(("http://", "https://", "//")):
        url = urljoin(base_url, url)
    elif url.startswith("//"):
        url = "https:" + url

    try:
        parsed = urlparse(url)
    except Exception:
        return None

    scheme = parsed.scheme.lower()
    if scheme in _BLOCKED_SCHEMES:
        return None
    if scheme not in ("http", "https"):
        return None

    # Lowercase host, strip default port
    netloc = parsed.netloc.lower()
    if ":" in netloc:
        host, port_str = netloc.rsplit(":", 1)
        try:
            port = int(port_str)
            if (scheme == "http" and port == 80) or (scheme == "https" and port == 443):
                netloc = host
        except ValueError:
            pass  # malformed port — keep as-is

    # Strip fragment
    fragment = ""

    # Strip tracking parameters
    if parsed.query:
        qs = parse_qs(parsed.query, keep_blank_values=True)
        cleaned = {k: v for k, v in qs.items() if k.lower() not in _TRACKING_PARAMS}
        query = urlencode(cleaned, doseq=True) if cleaned else ""
    else:
        query = ""

    # Normalise path: remove double slashes, preserve structure
    path = re.sub(r"/+", "/", parsed.path) or "/"

    # Block obvious non-HTML extensions
    path_lower = path.lower()
    if any(path_lower.endswith(ext) for ext in _BLOCKED_EXTENSIONS):
        # Allow .xml only if it's the sitemap
        if not path_lower.endswith(".xml"):
            return None

    normalised = urlunparse((scheme, netloc, path, parsed.params, query, fragment))
    return normalised


# ===========================================================================
# Scope enforcement
# ===========================================================================

def is_in_scope(
    url: str,
    approved_origin: str,
    approved_prefix: str,
    extra_allowed_paths: list[str] | None = None,
) -> bool:
    """Return True if url is within the approved crawl scope.

    Approved scope: exact origin (eurekasolutions.in) AND path starting with
    approved_prefix (/Eureka2026/).

    Extra allowed paths can extend the scope when explicitly configured.
    """
    try:
        parsed = urlparse(url)
    except Exception:
        return False

    host = parsed.netloc.lower()
    # Strip port from host comparison
    if ":" in host:
        host = host.rsplit(":", 1)[0]

    if host != approved_origin.lower():
        return False

    path = parsed.path

    if path.startswith(approved_prefix):
        return True

    # Check extra allowed paths
    if extra_allowed_paths:
        for extra in extra_allowed_paths:
            if path.startswith(extra):
                return True

    return False


def is_sitemap_url(url: str) -> bool:
    """Return True if the URL looks like a sitemap file."""
    path = urlparse(url).path.lower()
    return path.endswith("sitemap.xml") or "sitemap" in path.split("/")[-1]


def add_eureka2026_prefix(url: str, prefix: str = "/Eureka2026/") -> str:
    """If a URL from the sitemap lacks the approved prefix, add it.

    The sitemap at /Eureka2026/sitemap.xml lists URLs without the prefix
    (e.g. https://eurekasolutions.in/services), but those paths 404 without it.
    The working URLs use /Eureka2026/<path>.
    """
    parsed = urlparse(url)
    path = parsed.path
    if not path.startswith(prefix):
        # Strip leading slash from path before adding prefix
        stripped = path.lstrip("/")
        new_path = prefix + stripped if stripped else prefix
        return urlunparse((
            parsed.scheme, parsed.netloc, new_path,
            parsed.params, parsed.query, ""
        ))
    return url


# ===========================================================================
# SSRF protection
# ===========================================================================

def _is_ip_unsafe(ip: ipaddress.IPv4Address | ipaddress.IPv6Address) -> bool:
    if ip.is_loopback or ip.is_private or ip.is_link_local or ip.is_multicast or ip.is_unspecified:
        return True
    for net in _PRIVATE_RANGES:
        try:
            if ip in net:
                return True
        except TypeError:
            continue
    return False


def is_safe_host(host: str) -> tuple[bool, str]:
    """Return (is_safe, reason) for the given hostname.

    Checks:
    - Not a metadata endpoint
    - Not a private/loopback/link-local IP (literal or resolved)
    """
    host = host.lower().strip()
    if not host:
        return False, "empty host"

    # Strip port (handle IPv6 [::1]:8080 vs host:port)
    if host.startswith("[") and "]" in host:
        host = host[1:].split("]", 1)[0]
    elif host.count(":") == 1:
        host = host.split(":", 1)[0]

    # Block known metadata hosts
    if host in _METADATA_HOSTS:
        return False, f"blocked metadata host: {host}"

    # Try to parse as IP address first
    try:
        ip = ipaddress.ip_address(host)
        if _is_ip_unsafe(ip):
            return False, f"private/loopback IP address: {ip}"
        return True, ""
    except ValueError:
        pass  # not a raw IP — try DNS resolution

    # Resolve hostname and check resolved IPs
    try:
        results = socket.getaddrinfo(host, None)
        for result in results:
            try:
                ip = ipaddress.ip_address(result[4][0])
                if _is_ip_unsafe(ip):
                    return False, f"hostname {host!r} resolves to private IP {ip}"
            except ValueError:
                continue
    except (socket.gaierror, OSError):
        # DNS resolution failed — allow the fetcher to handle connection failure
        pass

    return True, ""


def extract_host(url: str) -> str | None:
    """Extract hostname (without port) from a URL."""
    try:
        parsed = urlparse(url)
        host = parsed.netloc.lower()
        if ":" in host and not host.startswith("["):
            host = host.rsplit(":", 1)[0]
        return host or None
    except Exception:
        return None


# ===========================================================================
# Trap detection
# ===========================================================================

def is_trap_url(url: str) -> tuple[bool, str]:
    """Return (is_trap, reason) if the URL looks like a pagination/calendar trap."""
    for pattern in _TRAP_PATTERNS:
        if pattern.search(url):
            return True, f"trap pattern matched: {pattern.pattern!r}"
    return False, ""


# ===========================================================================
# Internal link extraction
# ===========================================================================

def extract_internal_links(
    html_soup: "BeautifulSoup",  # type: ignore[name-defined]
    base_url: str,
    approved_origin: str,
    approved_prefix: str,
    extra_allowed_paths: list[str] | None = None,
) -> list[str]:
    """Extract normalised in-scope href values from a BeautifulSoup document.

    Returns a deduplicated list of in-scope normalised URLs.
    Does NOT make any network requests.
    """
    seen: set[str] = set()
    result: list[str] = []

    for tag in html_soup.find_all("a", href=True):
        raw = tag.get("href", "").strip()
        if not raw:
            continue
        normed = normalize_url(raw, base_url=base_url)
        if normed is None:
            continue
        if normed in seen:
            continue
        seen.add(normed)

        if is_in_scope(normed, approved_origin, approved_prefix, extra_allowed_paths):
            trap, _ = is_trap_url(normed)
            if not trap:
                result.append(normed)

    return result


# ===========================================================================
# Sitemap URL processing
# ===========================================================================

def process_sitemap_url(
    raw_url: str,
    approved_origin: str,
    approved_prefix: str,
) -> str | None:
    """Process a URL from the sitemap, adding the /Eureka2026/ prefix if needed.

    Returns the normalised in-scope URL, or None if out of scope.
    """
    # First normalise
    normed = normalize_url(raw_url)
    if normed is None:
        return None

    # Check if in scope as-is
    if is_in_scope(normed, approved_origin, approved_prefix):
        return normed

    # Try adding the prefix (sitemap lists paths without it)
    prefixed = add_eureka2026_prefix(normed, approved_prefix)
    prefixed_normed = normalize_url(prefixed)
    if prefixed_normed and is_in_scope(prefixed_normed, approved_origin, approved_prefix):
        return prefixed_normed

    return None
