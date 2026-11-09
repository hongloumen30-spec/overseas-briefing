"""Offline tests for the TokenHub integration; no real API key required."""

import os
import unittest
from unittest.mock import patch

import requests

from tokenhub_chat import (
    CHAT_COMPLETIONS_URL,
    MODEL_ID,
    TokenHubError,
    chat_completion,
)


class FakeResponse:
    def __init__(self, status, payload=None):
        self.status_code = status
        self.payload = payload or {}

    def json(self):
        return self.payload


class FakeSession:
    def __init__(self, responses):
        self.responses = iter(responses)
        self.calls = []

    def post(self, url, *, headers, json, timeout):
        self.calls.append((url, headers, json, timeout))
        return next(self.responses)


class TokenHubTests(unittest.TestCase):
    def test_missing_key_fails_before_http(self):
        with patch.dict(os.environ, {"TOKENHUB_API_KEY": ""}):
            with self.assertRaisesRegex(TokenHubError, "缺少 TOKENHUB_API_KEY"):
                chat_completion([{"role": "user", "content": "hi"}])

    def test_success_exact_model_and_auth(self):
        fake = FakeSession([FakeResponse(200, {"choices": [{"message": {"content": "连接成功"}}]})])
        with patch.dict(os.environ, {"TOKENHUB_API_KEY": "private-test-secret"}):
            output = chat_completion([{"role": "user", "content": "hi"}], session=fake)
        self.assertEqual(output, "连接成功")
        url, headers, body, timeout = fake.calls[0]
        self.assertEqual(url, CHAT_COMPLETIONS_URL)
        self.assertEqual(headers["Authorization"], "Bearer private-test-secret")
        self.assertEqual(body["model"], MODEL_ID)
        self.assertEqual(body["model"], "claude-opus-4-7-stable")
        self.assertFalse(body["stream"])
        self.assertEqual(timeout, 30)

    def test_status_errors_never_include_secret(self):
        for code in (401, 402, 429, 502):
            with self.subTest(status=code):
                fake = FakeSession([FakeResponse(code)])
                with patch.dict(os.environ, {"TOKENHUB_API_KEY": "private-test-secret"}):
                    with self.assertRaises(TokenHubError) as caught:
                        chat_completion([{"role": "user", "content": "hi"}], session=fake, max_retries=0)
                self.assertIn(str(code), str(caught.exception))
                self.assertNotIn("private-test-secret", str(caught.exception))

    def test_retries_with_bounded_exponential_backoff(self):
        fake = FakeSession([
            FakeResponse(429),
            FakeResponse(502),
            FakeResponse(200, {"choices": [{"message": {"content": "ok"}}]}),
        ])
        intervals = []
        with patch.dict(os.environ, {"TOKENHUB_API_KEY": "private-test-secret"}):
            result = chat_completion(
                [{"role": "user", "content": "hi"}],
                session=fake,
                max_retries=2,
                sleep=intervals.append,
            )
        self.assertEqual(result, "ok")
        self.assertEqual(intervals, [0.5, 1.0])
        self.assertEqual(len(fake.calls), 3)

    def test_retries_exhausted(self):
        fake = FakeSession([FakeResponse(502), FakeResponse(502), FakeResponse(502)])
        with patch.dict(os.environ, {"TOKENHUB_API_KEY": "private-test-secret"}):
            with self.assertRaisesRegex(TokenHubError, "502"):
                chat_completion(
                    [{"role": "user", "content": "hi"}],
                    session=fake, max_retries=2, sleep=lambda _: None,
                )
        self.assertEqual(len(fake.calls), 3)

    def test_network_error_is_redacted(self):
        class BadSession:
            def post(self, *args, **kwargs):
                raise requests.RequestException("private-test-secret should not be printed")

        with patch.dict(os.environ, {"TOKENHUB_API_KEY": "private-test-secret"}):
            with self.assertRaises(TokenHubError) as caught:
                chat_completion([{"role": "user", "content": "hi"}], session=BadSession())
        self.assertNotIn("private-test-secret", str(caught.exception))


if __name__ == "__main__":
    unittest.main()
