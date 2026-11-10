"""ASGI hosting for the TokenHub MCP App.

The upstream TokenHub API token and this MCP server's access token are DIFFERENT.
Never run a public instance without both configured as secret environment variables.
"""

import hmac
import os
import threading
import time
from collections import deque

from mcp.server.transport_security import TransportSecuritySettings
from starlette.requests import Request
from starlette.responses import JSONResponse, PlainTextResponse

from tokenhub_mcp.server import mcp


@mcp.custom_route("/health", methods=["GET"])
async def health(request: Request):
    """Public liveness check, never exposing credentials."""
    return JSONResponse({"status": "ok"})


class SecretBearerGuard:
    """Fail-closed ASGI bearer check + bounded per-process request budget."""

    def __init__(self, app, *, clock=time.monotonic, max_requests_per_minute=60):
        self.app = app
        self.clock = clock
        self.window = deque()
        self.lock = threading.Lock()
        self.limit = max_requests_per_minute

    @staticmethod
    def valid_token(authorization, expected):
        if not isinstance(authorization, str) or not authorization.startswith("Bearer "):
            return False
        supplied = authorization[7:]
        return bool(expected and supplied and hmac.compare_digest(supplied, expected))

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        # Free health checks are deliberately public, with no account data.
        if scope.get("path") == "/health":
            await self.app(scope, receive, send)
            return

        expected = os.environ.get("MCP_ACCESS_TOKEN", "")
        if len(expected) < 32:
            await PlainTextResponse("Server not configured", status_code=503)(scope, receive, send)
            return

        headers = dict(scope.get("headers", []))
        authorization = headers.get(b"authorization", b"").decode("latin-1")
        if not self.valid_token(authorization, expected):
            await PlainTextResponse(
                "Unauthorized",
                status_code=401,
                headers={"WWW-Authenticate": "Bearer"},
            )(scope, receive, send)
            return

        now = self.clock()
        with self.lock:
            while self.window and self.window[0] <= now - 60:
                self.window.popleft()
            if len(self.window) >= self.limit:
                allowed = False
            else:
                self.window.append(now)
                allowed = True
        if not allowed:
            await PlainTextResponse(
                "Too many MCP requests",
                status_code=429,
                headers={"Retry-After": "60"},
            )(scope, receive, send)
            return

        await self.app(scope, receive, send)


public_host = (os.environ.get("MCP_PUBLIC_HOST")
               or os.environ.get("RENDER_EXTERNAL_HOSTNAME") or "").strip()
hosts = ["localhost", "localhost:*", "127.0.0.1", "127.0.0.1:*", "[::1]", "[::1]:*"]
if public_host:
    if "/" in public_host or ":" in public_host:
        raise ValueError("MCP_PUBLIC_HOST must be hostname only, without scheme or port.")
    hosts.extend([public_host, f"{public_host}:*"])

security = TransportSecuritySettings(
    allowed_hosts=hosts,
    allowed_origins=["https://chatgpt.com", "https://chat.openai.com"],
)
app = SecretBearerGuard(
    mcp.streamable_http_app(
        transport_security=security,
        stateless_http=True,
        json_response=True,
        max_request_body_size=65536,
    )
)
