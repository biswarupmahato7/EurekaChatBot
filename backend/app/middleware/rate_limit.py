"""
backend/app/middleware/rate_limit.py
====================================
Proxy-aware in-memory rate limiter for the Eureka RAG FastAPI service.

Security guarantees:
- Derives client IP safely: only parses X-Forwarded-For if direct peer IP is in trusted_proxies.
- Emits standard 429 Too Many Requests response with Retry-After header.
- Uses sliding-window timestamps with periodic pruning to prevent memory exhaustion.
"""
from __future__ import annotations

import json
import logging
import time
from collections import defaultdict
from typing import Callable

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse, Response

logger = logging.getLogger(__name__)


def extract_client_ip(request: Request, trusted_proxies: list[str]) -> str:
    """Safely extract client IP respecting trusted proxy configuration."""
    direct_ip = request.client.host if request.client else "127.0.0.1"

    if not trusted_proxies or direct_ip not in trusted_proxies:
        return direct_ip

    # If direct peer is a trusted proxy, inspect X-Forwarded-For
    forwarded_for = request.headers.get("x-forwarded-for")
    if forwarded_for:
        ips = [ip.strip() for ip in forwarded_for.split(",") if ip.strip()]
        # Select the rightmost non-trusted IP in the chain
        for ip in reversed(ips):
            if ip not in trusted_proxies:
                return ip

    return direct_ip


class RateLimitMiddleware(BaseHTTPMiddleware):
    """In-memory sliding window rate limiter."""

    def __init__(
        self,
        app: Any,
        rate_limit_per_minute: int = 60,
        trusted_proxies: Optional[list[str]] = None,
    ) -> None:
        super().__init__(app)
        self.rate_limit_per_minute = rate_limit_per_minute
        self.trusted_proxies = trusted_proxies or []
        self._history: dict[str, list[float]] = defaultdict(list)
        self._last_cleanup = time.time()

    def _cleanup_old_records(self, now: float) -> None:
        """Evict records older than 60 seconds to bound memory usage."""
        if now - self._last_cleanup < 60.0:
            return
        cutoff = now - 60.0
        keys_to_delete: list[str] = []
        for ip, timestamps in self._history.items():
            valid = [ts for ts in timestamps if ts > cutoff]
            if valid:
                self._history[ip] = valid
            else:
                keys_to_delete.append(ip)
        for k in keys_to_delete:
            del self._history[k]
        self._last_cleanup = now

    def _resolve_client_ip(self, request: Request) -> str:
        """Resolve client IP respecting trusted proxy configuration."""
        return extract_client_ip(request, self.trusted_proxies)

    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        # Exclude health endpoints from rate limiting
        path = request.url.path
        if path.startswith("/health"):
            return await call_next(request)

        now = time.time()
        self._cleanup_old_records(now)

        client_ip = self._resolve_client_ip(request)
        cutoff = now - 60.0

        # Prune this IP's timestamps
        recent = [ts for ts in self._history[client_ip] if ts > cutoff]
        self._history[client_ip] = recent

        if len(recent) >= self.rate_limit_per_minute:
            logger.warning("Rate limit exceeded for client IP %s (limit: %d/min)", client_ip, self.rate_limit_per_minute)
            request_id = getattr(request.state, "request_id", "unknown")
            return JSONResponse(
                status_code=429,
                headers={
                    "Retry-After": "60",
                    "X-Request-ID": request_id,
                },
                content={
                    "request_id": request_id,
                    "error": {
                        "code": "rate_limit_exceeded",
                        "message": "Too many requests. Please wait a moment before trying again.",
                        "details": [],
                    },
                },
            )

        self._history[client_ip].append(now)
        return await call_next(request)
