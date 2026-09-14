import json
import unittest
from unittest.mock import patch

from fastapi import FastAPI, HTTPException, Request
from fastapi.testclient import TestClient

from app.db.session import get_db
from app.main import biz_handler, http_handler
from app.routers import account_recovery as recovery_router
from app.utils.api_locale import (
    localize_api_message,
    resolve_accept_language,
    resolve_request_locale,
)
from app.utils.response import BizError


def request_with_language(value: str | None) -> Request:
    headers = [] if value is None else [(b"accept-language", value.encode("ascii"))]
    return Request({
        "type": "http",
        "method": "GET",
        "path": "/test",
        "headers": headers,
    })


class ApiLocaleTests(unittest.IsolatedAsyncioTestCase):
    def test_supported_client_locales_and_quality_values_are_resolved(self):
        self.assertEqual(resolve_accept_language("zh-TW"), "zh-Hant")
        self.assertEqual(resolve_accept_language("zh-CN"), "zh-Hans")
        self.assertEqual(resolve_accept_language("en-US"), "en")
        self.assertEqual(
            resolve_accept_language("fr-FR, en-US;q=0.7, zh-TW;q=0.9"),
            "zh-Hant",
        )
        self.assertEqual(
            resolve_accept_language("en-US;q=0.9, zh-CN;q=1"),
            "zh-Hans",
        )
        self.assertEqual(resolve_accept_language("fr-FR"), "zh-Hant")
        self.assertEqual(resolve_accept_language(None), "zh-Hant")

    def test_unknown_business_copy_is_preserved(self):
        source = "未纳入第一批的业务错误"
        self.assertEqual(localize_api_message(source, "en"), source)

    def test_invalid_invite_code_is_localized_for_all_clients(self):
        source = "邀请码无效，请检查后重试"
        self.assertEqual(localize_api_message(source, "zh-Hant"), "邀請碼無效，請檢查後重試")
        self.assertEqual(localize_api_message(source, "zh-Hans"), source)
        self.assertEqual(
            localize_api_message(source, "en"),
            "The invitation code is invalid. Check it and try again.",
        )

    async def test_global_biz_error_translation_preserves_status_and_code(self):
        response = await biz_handler(
            request_with_language("en-US"),
            BizError("验证码错误或已过期", code=731, status_code=409),
        )
        body = json.loads(response.body)
        self.assertEqual(response.status_code, 409)
        self.assertEqual(body["code"], 731)
        self.assertEqual(body["msg"], "The verification code is invalid or has expired.")
        self.assertIsNone(body["data"])

    async def test_global_http_error_translation_preserves_headers(self):
        response = await http_handler(
            request_with_language("zh-TW"),
            HTTPException(
                status_code=429,
                detail="请求过于频繁，请稍后再试",
                headers={"Retry-After": "60"},
            ),
        )
        body = json.loads(response.body)
        self.assertEqual(response.status_code, 429)
        self.assertEqual(body["code"], 1)
        self.assertEqual(body["msg"], "請求過於頻繁，請稍後再試")
        self.assertEqual(response.headers["retry-after"], "60")

    async def test_request_locale_reads_the_header(self):
        self.assertEqual(resolve_request_locale(request_with_language("en-GB")), "en")


class RecoveryRouteLocaleTests(unittest.TestCase):
    def setUp(self):
        self.app = FastAPI()
        self.app.include_router(recovery_router.router)

        def fake_db():
            yield object()

        self.app.dependency_overrides[get_db] = fake_db
        self.client = TestClient(self.app)

    def tearDown(self):
        self.client.close()

    def test_generic_reset_result_stays_non_enumerating_in_each_language(self):
        expected = {
            "zh-TW": "若此電子郵件已綁定，重設郵件將在數分鐘內送達",
            "zh-CN": "如果该邮箱已绑定，重置邮件会在几分钟内送达",
            "en-US": "If this email address is linked to an account, a reset email will arrive within a few minutes.",
        }
        with patch.object(recovery_router, "limit_password_reset_request"), patch.object(
            recovery_router.recovery, "request_password_reset", return_value=None,
        ):
            for language, message in expected.items():
                with self.subTest(language=language):
                    headers = {"Accept-Language": language}
                    known = self.client.post(
                        "/api/auth/email/password-reset/request",
                        headers=headers,
                        json={"email": "known@example.com"},
                    )
                    unknown = self.client.post(
                        "/api/auth/email/password-reset/request",
                        headers=headers,
                        json={"email": "unknown@example.com"},
                    )
                    self.assertEqual(known.status_code, 200)
                    self.assertEqual(known.content, unknown.content)
                    self.assertEqual(known.json()["code"], 0)
                    self.assertEqual(known.json()["data"]["message"], message)
                    self.assertEqual(known.headers["cache-control"], "no-store")
                    self.assertEqual(known.headers["referrer-policy"], "no-referrer")

    def test_recovery_validation_error_is_localized_without_exposing_fields(self):
        response = self.client.post(
            "/api/auth/email/password-reset/request",
            headers={"Accept-Language": "en-US"},
            json={"email": "not-an-email"},
        )
        self.assertEqual(response.status_code, 422)
        self.assertEqual(response.json(), {
            "code": 1,
            "msg": "The account recovery request is invalid. Check it and try again.",
            "data": None,
        })
        self.assertEqual(response.headers["cache-control"], "no-store")
        self.assertEqual(response.headers["referrer-policy"], "no-referrer")

    def test_recovery_biz_error_preserves_code_status_and_security_headers(self):
        with patch.object(recovery_router, "limit_password_reset_request"), patch.object(
            recovery_router.recovery,
            "request_password_reset",
            side_effect=BizError("邮箱服务尚未配置", code=50320, status_code=503),
        ):
            response = self.client.post(
                "/api/auth/email/password-reset/request",
                headers={"Accept-Language": "en-US"},
                json={"email": "known@example.com"},
            )
        self.assertEqual(response.status_code, 503)
        self.assertEqual(response.json(), {
            "code": 50320,
            "msg": "The email service is not configured.",
            "data": None,
        })
        self.assertEqual(response.headers["cache-control"], "no-store")
        self.assertEqual(response.headers["referrer-policy"], "no-referrer")


if __name__ == "__main__":
    unittest.main()
