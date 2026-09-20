import unittest
from types import SimpleNamespace
from unittest.mock import patch

from fastapi import FastAPI
from fastapi.testclient import TestClient
from starlette.requests import Request

from app.core.config import Settings, settings
from app.routers.payment import checkout as mapay_checkout
from app.routers.payment import create_payment as create_mapay_payment
from app.routers.platform import router as platform_router
from app.routers.qixiang_payment import checkout as qixiang_checkout
from app.routers.qixiang_payment import create_payment as create_qixiang_payment
from app.routers.withdrawal import create as create_withdrawal
from app.schemas.payment import RechargePaymentCreateIn
from app.schemas.withdrawal import WithdrawalCreateIn
from app.services.trade_mode import (
    RECHARGE_DISABLED_MESSAGE,
    WITHDRAWAL_DISABLED_MESSAGE,
    platform_capabilities,
)
from app.utils.response import BizError


class _FailIfDatabaseIsTouched:
    def __getattr__(self, name: str):
        raise AssertionError(f"database access must not occur while capability is disabled: {name}")


class PlatformCapabilityTests(unittest.TestCase):
    def setUp(self):
        self.original = {
            name: getattr(settings, name)
            for name in (
                "DIRECT_TRADE_ENABLED",
                "MATCHMAKING_ENABLED",
                "MATCHMAKING_CREDENTIAL_ESCROW_ENABLED",
                "PAYMENT_SERVICE_ENABLED",
                "QIXIANGPAY_ENABLED",
                "MAPAY_ENABLED",
                "MANUAL_PAYOUT_ENABLED",
            )
        }
        settings.DIRECT_TRADE_ENABLED = False
        settings.MATCHMAKING_ENABLED = True
        settings.MATCHMAKING_CREDENTIAL_ESCROW_ENABLED = True
        settings.PAYMENT_SERVICE_ENABLED = True
        settings.QIXIANGPAY_ENABLED = True
        settings.MAPAY_ENABLED = True
        settings.MANUAL_PAYOUT_ENABLED = True
        self.user = SimpleNamespace(id=1)
        self.db = _FailIfDatabaseIsTouched()
        self.request = Request({
            "type": "http",
            "method": "GET",
            "scheme": "https",
            "path": "/",
            "query_string": b"",
            "headers": [],
            "client": ("127.0.0.1", 1234),
            "server": ("testserver", 443),
        })

    def tearDown(self):
        for name, value in self.original.items():
            setattr(settings, name, value)

    def test_defaults_are_safe_for_a_matchmaking_launch(self):
        self.assertIs(Settings.model_fields["DIRECT_TRADE_ENABLED"].default, False)
        self.assertIs(Settings.model_fields["MATCHMAKING_ENABLED"].default, True)
        self.assertIs(
            Settings.model_fields["MATCHMAKING_CREDENTIAL_ESCROW_ENABLED"].default,
            True,
        )

    def test_public_endpoint_is_unauthenticated_and_effective_flags_fail_closed(self):
        app = FastAPI()
        app.include_router(platform_router)
        with (
            patch("app.services.trade_mode.sensitive_security_errors", return_value=()),
            TestClient(app) as client,
        ):
            response = client.get("/api/platform/capabilities")

        self.assertEqual(response.status_code, 200, response.text)
        data = response.json()["data"]
        self.assertEqual(data["commerce_mode"], "matchmaking")
        self.assertTrue(data["matchmaking_enabled"])
        self.assertTrue(data["credential_escrow_enabled"])
        self.assertFalse(data["direct_trade_enabled"])
        self.assertFalse(data["payment_enabled"])
        self.assertFalse(data["recharge_enabled"])
        self.assertFalse(data["withdraw_enabled"])
        self.assertTrue(data["history_read_enabled"])

    def test_credential_escrow_fails_closed_when_sensitive_config_is_unsafe(self):
        with patch(
            "app.services.trade_mode.sensitive_security_errors",
            return_value=("missing_sensitive_data_key",),
        ):
            data = platform_capabilities()

        self.assertTrue(data["matchmaking_enabled"])
        self.assertFalse(data["credential_escrow_enabled"])
        self.assertFalse(data["direct_trade_enabled"])

    def test_effective_financial_flags_require_direct_trade_and_sub_capabilities(self):
        settings.DIRECT_TRADE_ENABLED = True
        with (
            patch("app.services.payment_gateway.provider_configured", return_value=True),
            patch("app.services.trade_mode.sensitive_capability_enabled", return_value=True),
        ):
            data = platform_capabilities()

        self.assertEqual(data["commerce_mode"], "direct_trade")
        self.assertTrue(data["payment_enabled"])
        self.assertTrue(data["recharge_enabled"])
        self.assertTrue(data["withdraw_enabled"])

    def test_only_new_recharge_and_withdrawal_are_blocked_before_database_access(self):
        recharge = RechargePaymentCreateIn(amount_cny=10, payment_type="alipay")
        withdrawal = WithdrawalCreateIn(
            amount_card_hours=10,
            bank_card_id=1,
            client_request_id="withdraw-0001",
        )
        actions = {
            "qixiang recharge": lambda: create_qixiang_payment(
                recharge, self.user, self.db, "android"
            ),
            "withdrawal": lambda: create_withdrawal(
                withdrawal, self.user, self.db, "android"
            ),
        }

        for label, action in actions.items():
            with self.subTest(label=label):
                with self.assertRaises(BizError) as blocked:
                    action()
                self.assertEqual(blocked.exception.status_code, 503)
                self.assertIn(
                    blocked.exception.msg,
                    {RECHARGE_DISABLED_MESSAGE, WITHDRAWAL_DISABLED_MESSAGE},
                )

        with self.assertRaises(BizError) as retired:
            create_mapay_payment(recharge, self.user, self.db, "android")
        self.assertEqual(retired.exception.status_code, 410)
        self.assertIn("停止创建", retired.exception.msg)

    def test_qixiang_checkout_remains_available_but_mapay_checkout_is_tombstoned(self):
        with self.assertRaises(BizError) as retired:
            mapay_checkout("existing-token", self.db)
        self.assertEqual(retired.exception.status_code, 410)
        self.assertIn("历史订单仅支持查询", retired.exception.msg)

        with patch(
            "app.routers.qixiang_payment.checkout_redirect_url",
            return_value="https://pay.example.test/existing",
        ):
            response = qixiang_checkout("existing-token", self.request, self.db)
        self.assertEqual(response.status_code, 303)

    def test_history_only_mode_is_explicit(self):
        settings.MATCHMAKING_ENABLED = False
        data = platform_capabilities()
        self.assertEqual(data["commerce_mode"], "history_only")
        self.assertFalse(data["matchmaking_enabled"])
        self.assertFalse(data["credential_escrow_enabled"])
        self.assertTrue(data["history_read_enabled"])


if __name__ == "__main__":
    unittest.main()
