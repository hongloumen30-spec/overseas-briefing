"""Pure offline tests for ASGI boundary; requires no actual upstream key."""

import unittest
from unittest.mock import patch

from tokenhub_mcp.asgi import SecretBearerGuard


class FakeDownstream:
    def __init__(self):
        self.calls = 0

    async def __call__(self, scope, receive, send):
        self.calls += 1
        await send({"type": "http.response.start", "status": 200, "headers": []})
        await send({"type": "http.response.body", "body": b"ok"})


async def call_http(app, authorization=None, path="/mcp"):
    headers = []
    if authorization is not None:
        headers.append((b"authorization", authorization.encode("latin-1")))
    scope = {
        "type": "http", "asgi": {"version": "3.0"},
        "http_version": "1.1", "method": "POST",
        "scheme": "http", "path": path, "raw_path": path.encode(),
        "query_string": b"", "headers": headers, "client": ("127.0.0.1", 2345),
        "server": ("127.0.0.1", 8000),
    }
    messages = []

    async def receive():
        return {"type": "http.request", "body": b"", "more_body": False}

    async def send(message):
        messages.append(message)

    await app(scope, receive, send)
    return next(m["status"] for m in messages if m["type"] == "http.response.start")


class GuardTests(unittest.IsolatedAsyncioTestCase):
    async def test_missing_server_secret_fails_closed(self):
        downstream = FakeDownstream()
        app = SecretBearerGuard(downstream)
        with patch.dict("os.environ", {"MCP_ACCESS_TOKEN": ""}):
            code = await call_http(app, "Bearer fake")
        self.assertEqual(code, 503)
        self.assertEqual(downstream.calls, 0)

    async def test_only_separate_mcp_secret_works(self):
        secret = "a" * 40
        downstream = FakeDownstream()
        app = SecretBearerGuard(downstream)
        with patch.dict("os.environ", {"MCP_ACCESS_TOKEN": secret}):
            self.assertEqual(await call_http(app), 401)
            self.assertEqual(await call_http(app, "Bearer wrong"), 401)
            self.assertEqual(await call_http(app, "Bearer " + secret), 200)
        self.assertEqual(downstream.calls, 1)

    async def test_rate_limit(self):
        secret = "b" * 40
        downstream = FakeDownstream()
        app = SecretBearerGuard(downstream, max_requests_per_minute=2)
        with patch.dict("os.environ", {"MCP_ACCESS_TOKEN": secret}):
            codes = [await call_http(app, "Bearer " + secret) for _ in range(3)]
        self.assertEqual(codes, [200, 200, 429])
        self.assertEqual(downstream.calls, 2)

    async def test_health_does_not_require_credentials(self):
        downstream = FakeDownstream()
        app = SecretBearerGuard(downstream)
        with patch.dict("os.environ", {"MCP_ACCESS_TOKEN": ""}):
            self.assertEqual(await call_http(app, path="/health"), 200)
        self.assertEqual(downstream.calls, 1)


if __name__ == "__main__":
    unittest.main()
