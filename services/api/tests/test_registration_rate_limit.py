import unittest
from unittest.mock import Mock, patch

from fastapi import HTTPException

from app.routers.auth import register
from app.schemas.user import RegisterIn
from app.utils.response import BizError


class RegistrationRateLimitTests(unittest.TestCase):
    @staticmethod
    def registration_data() -> RegisterIn:
        return RegisterIn(
            username="限流测试用户",
            phone="13900000061",
            password="test-password",
            captcha_key="test-key",
            captcha_code="A2BC",
        )

    def test_invalid_captcha_does_not_spend_phone_quota(self):
        order: list[str] = []
        with (
            patch("app.routers.auth.limit_register_request", side_effect=lambda: order.append("global")),
            patch(
                "app.routers.auth.ensure_register_account_available",
                side_effect=lambda _phone: order.append("account-preflight"),
            ),
            patch("app.routers.auth.resolve_client", side_effect=lambda _client: ("legacy", None)),
            patch("app.routers.auth.verify_captcha", side_effect=lambda *_args: order.append("captcha") or False),
            patch("app.routers.auth.limit_register_account") as account_limit,
            self.assertRaises(BizError) as caught,
        ):
            register(self.registration_data(), Mock())

        self.assertEqual(caught.exception.msg, "验证码错误或已过期")
        self.assertEqual(order, ["global", "account-preflight", "captcha"])
        account_limit.assert_not_called()

    def test_full_phone_bucket_does_not_consume_captcha(self):
        limited = HTTPException(status_code=429, detail="请求过于频繁，请稍后再试")
        with (
            patch("app.routers.auth.limit_register_request"),
            patch("app.routers.auth.ensure_register_account_available", side_effect=limited),
            patch("app.routers.auth.verify_captcha") as verify,
            patch("app.routers.auth.limit_register_account") as account_limit,
            self.assertRaises(HTTPException) as caught,
        ):
            register(self.registration_data(), Mock())

        self.assertEqual(caught.exception.status_code, 429)
        verify.assert_not_called()
        account_limit.assert_not_called()

    def test_valid_captcha_records_phone_attempt_after_consumption(self):
        order: list[str] = []
        limited = HTTPException(status_code=429, detail="请求过于频繁，请稍后再试")

        def record_account_limit(phone: str):
            order.append(f"account:{phone}")
            raise limited

        with (
            patch("app.routers.auth.limit_register_request", side_effect=lambda: order.append("global")),
            patch(
                "app.routers.auth.ensure_register_account_available",
                side_effect=lambda _phone: order.append("account-preflight"),
            ),
            patch("app.routers.auth.resolve_client", side_effect=lambda _client: ("legacy", None)),
            patch("app.routers.auth.verify_captcha", side_effect=lambda *_args: order.append("captcha") or True),
            patch("app.routers.auth.limit_register_account", side_effect=record_account_limit),
            self.assertRaises(HTTPException) as caught,
        ):
            register(self.registration_data(), Mock())

        self.assertEqual(caught.exception.status_code, 429)
        self.assertEqual(
            order,
            ["global", "account-preflight", "captcha", "account:13900000061"],
        )


if __name__ == "__main__":
    unittest.main()
