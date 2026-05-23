import io
import json
import socket
import sys
import unittest
from pathlib import Path
from urllib.error import HTTPError


BACKEND_DIR = Path(__file__).resolve().parents[1] / "backend"
sys.path.insert(0, str(BACKEND_DIR))


class V4AIProviderTest(unittest.TestCase):
    def test_base_url_root_is_normalized_to_chat_completions_endpoint(self):
        import ai_provider

        seen = {}

        def fake_urlopen(req, timeout):
            seen["url"] = req.full_url
            return _Response({"choices": [{"message": {"content": "{}"}}]})

        original = ai_provider.request.urlopen
        ai_provider.request.urlopen = fake_urlopen
        try:
            ai_provider.call_openai_compatible({"model": "demo"}, "sk-test", base_url="https://example.com/v1")
        finally:
            ai_provider.request.urlopen = original

        self.assertEqual(seen["url"], "https://example.com/v1/chat/completions")

    def test_unauthorized_response_returns_actionable_error_without_key(self):
        import ai_provider

        def fake_urlopen(req, timeout):
            raise HTTPError(
                req.full_url,
                401,
                "Unauthorized",
                {},
                io.BytesIO(b'{"error":{"message":"invalid api key"}}'),
            )

        original = ai_provider.request.urlopen
        ai_provider.request.urlopen = fake_urlopen
        try:
            with self.assertRaises(ValueError) as raised:
                ai_provider.call_openai_compatible({"model": "demo"}, "sk-secret", base_url="https://example.com/v1")
        finally:
            ai_provider.request.urlopen = original

        message = str(raised.exception)
        self.assertIn("模型服务鉴权失败", message)
        self.assertIn("Base URL", message)
        self.assertNotIn("sk-secret", message)

    def test_read_timeout_returns_actionable_error_without_key(self):
        import ai_provider

        def fake_urlopen(req, timeout):
            self.assertGreaterEqual(timeout, 180)
            return _TimeoutResponse()

        original = ai_provider.request.urlopen
        ai_provider.request.urlopen = fake_urlopen
        try:
            with self.assertRaises(ValueError) as raised:
                ai_provider.call_openai_compatible({"model": "demo"}, "sk-secret", base_url="https://example.com/v1")
        finally:
            ai_provider.request.urlopen = original

        message = str(raised.exception)
        self.assertIn("模型服务响应超时", message)
        self.assertIn("稍后重试", message)
        self.assertNotIn("sk-secret", message)


class _Response:
    def __init__(self, payload):
        self.payload = payload

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False

    def read(self):
        return json.dumps(self.payload).encode("utf-8")


class _TimeoutResponse:
    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False

    def read(self):
        raise socket.timeout("The read operation timed out")


if __name__ == "__main__":
    unittest.main()
