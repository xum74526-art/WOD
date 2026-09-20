import asyncio
import json
import re
import unittest
from pathlib import Path
from unittest.mock import patch

from fastapi import FastAPI, Request

from app.core.request_body_limit import (
    REGISTRATION_BODY_MAX_BYTES,
    RegistrationBodyLimitRoute,
)
from app.main import app
from app.routers.auth import router as auth_router


async def invoke_asgi(
    application,
    path: str,
    chunks: list[bytes],
    *,
    headers: list[tuple[bytes, bytes]] | None = None,
    forbid_receive: bool = False,
):
    pending = [
        {
            "type": "http.request",
            "body": chunk,
            "more_body": index < len(chunks) - 1,
        }
        for index, chunk in enumerate(chunks)
    ]
    receive_calls = 0
    sent = []

    async def receive():
        nonlocal receive_calls
        receive_calls += 1
        if forbid_receive:
            raise AssertionError("oversized Content-Length must be rejected before reading")
        if pending:
            return pending.pop(0)
        return {"type": "http.disconnect"}

    async def send(message):
        sent.append(message)

    scope = {
        "type": "http",
        "asgi": {"version": "3.0", "spec_version": "2.3"},
        "http_version": "1.1",
        "method": "POST",
        "scheme": "https",
        "path": path,
        "raw_path": path.encode("ascii"),
        "query_string": b"",
        "root_path": "",
        "headers": headers or [],
        "client": ("127.0.0.1", 12345),
        "server": ("testserver", 443),
        "state": {},
    }
    await application(scope, receive, send)
    response_start = next(message for message in sent if message["type"] == "http.response.start")
    response_body = b"".join(
        message.get("body", b"")
        for message in sent
        if message["type"] == "http.response.body"
    )
    return response_start["status"], response_body, receive_calls


class RegistrationBodyLimitTests(unittest.TestCase):
    def test_declared_oversize_is_rejected_before_business_or_body_read(self):
        headers = [
            (b"content-type", b"application/json"),
            (b"content-length", str(REGISTRATION_BODY_MAX_BYTES + 1).encode("ascii")),
            (b"accept-language", b"en-US"),
        ]
        with patch("app.routers.auth.limit_register_request") as rate_limit, patch(
            "app.routers.auth.verify_captcha",
        ) as verify_captcha:
            status_code, response_body, receive_calls = asyncio.run(invoke_asgi(
                app,
                "/api/auth/register",
                [],
                headers=headers,
                forbid_receive=True,
            ))

        self.assertEqual(status_code, 413)
        self.assertEqual(receive_calls, 0)
        self.assertEqual(json.loads(response_body), {
            "code": 1,
            "msg": "The registration details are too long. Shorten them and try again.",
            "data": None,
        })
        rate_limit.assert_not_called()
        verify_captcha.assert_not_called()

    def test_missing_or_forged_length_is_rejected_by_actual_bytes_without_reflection(self):
        sentinel = b"private-password-marker"
        chunks = [b"{" + sentinel + b":" + b"x" * 8_000, b"y" * 8_500 + b"}"]
        for length_headers in ([], [(b"content-length", b"1")]):
            with self.subTest(headers=length_headers), patch(
                "app.routers.auth.limit_register_request",
            ) as rate_limit, patch("app.routers.auth.verify_captcha") as verify_captcha:
                status_code, response_body, receive_calls = asyncio.run(invoke_asgi(
                    app,
                    "/api/auth/register",
                    chunks,
                    headers=[(b"content-type", b"application/json"), *length_headers],
                ))

                self.assertEqual(status_code, 413)
                self.assertGreaterEqual(receive_calls, 2)
                self.assertNotIn(sentinel, response_body)
                self.assertLess(len(response_body), 256)
                rate_limit.assert_not_called()
                verify_captcha.assert_not_called()

    def test_exact_limit_reaches_the_limited_endpoint(self):
        limited_app = FastAPI()

        async def echo_size(request: Request):
            return {"size": len(await request.body())}

        limited_app.router.add_api_route(
            "/limited",
            echo_size,
            methods=["POST"],
            route_class_override=RegistrationBodyLimitRoute,
        )
        body = b"x" * REGISTRATION_BODY_MAX_BYTES
        status_code, response_body, _ = asyncio.run(invoke_asgi(
            limited_app,
            "/limited",
            [body[:8_000], body[8_000:]],
            headers=[(b"content-type", b"application/octet-stream")],
        ))

        self.assertEqual(status_code, 200)
        self.assertEqual(json.loads(response_body), {"size": REGISTRATION_BODY_MAX_BYTES})

    def test_only_registration_uses_the_limited_route(self):
        registration = next(route for route in auth_router.routes if getattr(route, "path", None) == "/api/auth/register")
        login = next(route for route in auth_router.routes if getattr(route, "path", None) == "/api/auth/login")
        self.assertIsInstance(registration, RegistrationBodyLimitRoute)
        self.assertNotIsInstance(login, RegistrationBodyLimitRoute)

    def test_nginx_limits_only_the_two_public_registration_entries(self):
        repository = Path(__file__).resolve().parents[3]
        nginx = (repository / "infra" / "kai-nginx.conf").read_text(encoding="utf-8")
        for path, upstream in (
            ("/api/v1/auth/password/register", "127.0.0.1:3000"),
            ("/api/auth/register", "127.0.0.1:8000"),
        ):
            block = re.search(rf"location = {re.escape(path)} \{{(?P<body>.*?)\n    \}}", nginx, re.DOTALL)
            self.assertIsNotNone(block)
            self.assertIn("client_max_body_size 32k;", block.group("body"))
            self.assertIn(f"proxy_pass http://{upstream};", block.group("body"))
            self.assertIn("error_page 413 = @registration_payload_too_large;", block.group("body"))
        for trailing_path, canonical_path in (
            ("/api/v1/auth/password/register/", "/api/v1/auth/password/register"),
            ("/api/auth/register/", "/api/auth/register"),
        ):
            block = re.search(rf"location = {re.escape(trailing_path)} \{{(?P<body>.*?)\n    \}}", nginx, re.DOTALL)
            self.assertIsNotNone(block)
            self.assertIn("client_max_body_size 32k;", block.group("body"))
            self.assertIn(f"return 308 {canonical_path};", block.group("body"))
        self.assertIn("client_max_body_size 21m;", nginx)
        self.assertIn("location = /api/community/media/upload", nginx)


if __name__ == "__main__":
    unittest.main()
