"""
backend/app/middleware/request_id.py
====================================
Request ID middleware generating and attaching correlation IDs to requests and responses.
"""
from __future__ import annotations

import re
import uuid
from typing import Callable

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

_REQUEST_ID_REGEX = re.compile(r"^[a-zA-Z0-9_\-]{8,64}$")


class RequestIdMiddleware(BaseHTTPMiddleware):
    """Assigns or validates a unique request_id for correlation tracking."""

    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        # Check client header if provided
        client_req_id = request.headers.get("x-request-id") or request.headers.get("X-Request-ID")
        if client_req_id and _REQUEST_ID_REGEX.match(client_req_id):
            request_id = client_req_id
        else:
            request_id = f"req-{uuid.uuid4().hex[:16]}"

        # Store in request state for downstream handlers
        request.state.request_id = request_id

        response = await call_next(request)

        # Ensure response contains X-Request-ID header
        response.headers["X-Request-ID"] = request_id
        return response
