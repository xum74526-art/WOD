import base64
import html
import re
import tempfile
import threading
import unittest
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from pathlib import Path
from unittest.mock import patch
from zoneinfo import ZoneInfo

from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import padding, rsa
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool
from pydantic import ValidationError

from app.core.config import settings
from app.db.base import Base
from app.models import Ledger, PaymentOrder, User, Wallet  # noqa: F401
from app.schemas.payment import RechargePaymentCreateIn
from app.services.mapay import (
    _verify_query_response,
    canonicalize,
    checkout_html,
    create_recharge_order,
    expire_pending_payment_orders,
    handle_notification,
    legacy_reconciliation_configured,
    payment_status,
    provider_configured,
    public_config,
    query_provider_and_reconcile,
    utc_now,
    verify_params,
)
from app.services.payment_gateway import (
    assert_payment_configuration_safe,
    payment_readiness_errors,
)
from app.utils.response import BizError


class MaPayPaymentTests(unittest.TestCase):
    def setUp(self):
        self.engine = create_engine(
            "sqlite://",
            connect_args={"check_same_thread": False},
            poolclass=StaticPool,
        )
        Base.metadata.create_all(self.engine)
        self.db = sessionmaker(bind=self.engine)()
        self.user = User(phone="13900000901", username="支付测试", password="!")
        self.db.add(self.user)
        self.db.flush()
        self.wallet = Wallet(user_id=self.user.id, balance=Decimal("10"), frozen=Decimal("0"))
        self.db.add(self.wallet)
        self.db.commit()

        self.tempdir = tempfile.TemporaryDirectory()
        root = Path(self.tempdir.name)
        self.merchant_private = rsa.generate_private_key(public_exponent=65537, key_size=2048)
        self.platform_private = rsa.generate_private_key(public_exponent=65537, key_size=2048)
        merchant_path = root / "merchant-private.pem"
        platform_path = root / "platform-public.pem"
        merchant_path.write_bytes(self.merchant_private.private_bytes(
            serialization.Encoding.PEM,
            serialization.PrivateFormat.PKCS8,
            serialization.NoEncryption(),
        ))
        platform_path.write_bytes(self.platform_private.public_key().public_bytes(
            serialization.Encoding.PEM,
            serialization.PublicFormat.SubjectPublicKeyInfo,
        ))

        self.original = {
            name: getattr(settings, name)
            for name in (
                "PAYMENT_SERVICE_ENABLED", "MAPAY_ENABLED",
                "MAPAY_LEGACY_RECONCILIATION_ENABLED", "MAPAY_BASE_URL", "MAPAY_PID",
                "MAPAY_MERCHANT_PRIVATE_KEY_PATH", "MAPAY_PLATFORM_PUBLIC_KEY_PATH",
                "MAPAY_NOTIFY_URL", "MAPAY_PUBLIC_API_BASE_URL", "MAPAY_PAYMENT_TYPES",
                "MAPAY_HTTP_TIMEOUT", "MAPAY_CHECKOUT_TTL_SECONDS", "MAPAY_PROVIDER_TIMEZONE",
                "CARD_HOUR_RMB_RATE",
                "MAPAY_MIN_AMOUNT_CNY", "MAPAY_MAX_AMOUNT_CNY",
            )
        }
        settings.PAYMENT_SERVICE_ENABLED = True
        settings.MAPAY_ENABLED = True
        settings.MAPAY_LEGACY_RECONCILIATION_ENABLED = True
        settings.MAPAY_BASE_URL = "https://mzf.mapay.cc/xpay/epayn"
        settings.MAPAY_PID = "10001"
        settings.MAPAY_MERCHANT_PRIVATE_KEY_PATH = str(merchant_path)
        settings.MAPAY_PLATFORM_PUBLIC_KEY_PATH = str(platform_path)
        settings.MAPAY_NOTIFY_URL = "https://example.test/api/payments/mapay/notify"
        settings.MAPAY_PUBLIC_API_BASE_URL = "https://example.test/api"
        settings.MAPAY_PAYMENT_TYPES = "alipay,wxpay"
        settings.MAPAY_HTTP_TIMEOUT = 10
        settings.MAPAY_CHECKOUT_TTL_SECONDS = 300
        settings.MAPAY_PROVIDER_TIMEZONE = "Asia/Shanghai"
        settings.CARD_HOUR_RMB_RATE = 1.002
        settings.MAPAY_MIN_AMOUNT_CNY = 0.01
        settings.MAPAY_MAX_AMOUNT_CNY = 50000

    def tearDown(self):
        for name, value in self.original.items():
            setattr(settings, name, value)
        self.db.close()
        self.tempdir.cleanup()

    def _platform_sign(self, params: dict) -> str:
        signature = self.platform_private.sign(
            canonicalize(params).encode("utf-8"),
            padding.PKCS1v15(),
            hashes.SHA256(),
        )
        return base64.b64encode(signature).decode("ascii")

    def _paid_params(self, order: PaymentOrder, money: str = "0.01") -> dict:
        params = {
            "pid": "10001",
            "trade_no": "MAPAY-TEST-0001",
            "out_trade_no": order.order_no,
            "type": "alipay",
            "name": "算力星图钱包卡时充值",
            "money": money,
            "trade_status": "TRADE_SUCCESS",
            "param": order.order_no,
            "sign_type": "RSA",
        }
        params["sign"] = self._platform_sign(params)
        return params

    @staticmethod
    def _provider_local_time(utc_value: datetime) -> str:
        aware = utc_value.replace(tzinfo=timezone.utc)
        return aware.astimezone(ZoneInfo("Asia/Shanghai")).strftime("%Y-%m-%d %H:%M:%S")

    def test_v2_signature_canonicalization_excludes_signature_and_empty_values(self):
        self.assertEqual(
            canonicalize({"z": "2", "a": "1", "sign": "x", "sign_type": "RSA", "empty": ""}),
            "a=1&z=2",
        )

    def test_recharge_request_requires_supported_payment_type(self):
        with self.assertRaises(ValidationError):
            RechargePaymentCreateIn(amount_cny="0.01")
        with self.assertRaises(ValidationError):
            RechargePaymentCreateIn(amount_cny="0.01", payment_type="bank")

        payload = RechargePaymentCreateIn(amount_cny="0.01", payment_type="wxpay")
        self.assertEqual(payload.payment_type, "wxpay")

    def test_configured_ten_yuan_minimum_is_enforced(self):
        settings.MAPAY_MIN_AMOUNT_CNY = 10
        self.assertEqual(public_config()["min_amount_cny"], 10.0)
        with self.assertRaises(BizError):
            create_recharge_order(
                self.db,
                self.user.id,
                Decimal("9.99"),
                payment_type="alipay",
            )
        output = create_recharge_order(
            self.db,
            self.user.id,
            Decimal("10"),
            payment_type="alipay",
        )
        self.assertEqual(output["amount_cny"], 10.0)

    def test_only_configured_payment_types_are_public_and_accepted(self):
        settings.MAPAY_PAYMENT_TYPES = " wxpay,wxpay,unknown "
        config = public_config()
        self.assertTrue(config["enabled"])
        self.assertEqual(config["payment_types"], ["wxpay"])

        with self.assertRaisesRegex(BizError, "当前不可用") as disabled_channel:
            create_recharge_order(
                self.db,
                self.user.id,
                Decimal("0.01"),
                payment_type="alipay",
            )
        self.assertEqual(disabled_channel.exception.status_code, 400)
        self.assertEqual(self.db.query(PaymentOrder).count(), 0)

        output = create_recharge_order(
            self.db,
            self.user.id,
            Decimal("0.01"),
            payment_type="wxpay",
        )
        self.assertEqual(output["channel"], "wxpay")

        settings.MAPAY_PAYMENT_TYPES = ""
        self.assertFalse(provider_configured())
        self.assertEqual(public_config()["payment_types"], [])

    def test_query_response_supports_provider_signed_subset_but_notifications_stay_strict(self):
        payload = {
            "code": 0,
            "msg": "success",
            "trade_no": "MAPAY-QUERY-0001",
            "out_trade_no": "WODR-QUERY-0001",
            "status": 0,
            "type": "alipay",
            "pid": "10001",
            "money": "0.01",
            "timestamp": "1787129849",
            "sign_type": "RSA",
        }
        signature = self.platform_private.sign(
            canonicalize(
                payload,
                exclude_fields={"code", "status"},
            ).encode("utf-8"),
            padding.PKCS1v15(),
            hashes.SHA256(),
        )
        payload["sign"] = base64.b64encode(signature).decode("ascii")

        self.assertTrue(_verify_query_response(payload))
        self.assertFalse(verify_params(payload))

        tampered = dict(payload)
        tampered["money"] = "1.00"
        self.assertFalse(_verify_query_response(tampered))

    def test_create_checkout_and_verified_notification_credit_exactly_once(self):
        self.assertTrue(provider_configured())
        output = create_recharge_order(
            self.db,
            self.user.id,
            Decimal("0.01"),
            payment_type="alipay",
        )
        self.assertEqual(output["amount_cny"], 0.01)
        self.assertEqual(output["card_hours"], 0.00998)
        token = output["checkout_url"].rsplit("/", 1)[-1]
        page = checkout_html(self.db, token)
        self.assertIn("/api/pay/submit", page)
        self.assertIn("RSA", page)
        self.assertNotIn("PRIVATE KEY", page)

        hidden_fields = {
            html.unescape(key): html.unescape(value)
            for key, value in re.findall(r'name="([^"]+)" value="([^"]*)"', page)
        }
        self.assertEqual(hidden_fields["type"], "alipay")
        self.assertEqual(hidden_fields["name"], "算力星图钱包卡时充值")
        merchant_public = self.merchant_private.public_key()
        merchant_public.verify(
            base64.b64decode(hidden_fields.pop("sign"), validate=True),
            canonicalize(hidden_fields).encode("utf-8"),
            padding.PKCS1v15(),
            hashes.SHA256(),
        )

        order = self.db.query(PaymentOrder).filter_by(order_no=output["order_no"]).one()
        self.assertEqual(order.channel, "alipay")
        params = self._paid_params(order)
        self.assertTrue(handle_notification(self.db, params))
        self.assertTrue(handle_notification(self.db, params))

        self.db.refresh(self.wallet)
        self.db.refresh(order)
        self.assertEqual(self.wallet.balance, Decimal("10.009980"))
        self.assertEqual(order.status, "paid")
        self.assertIsNotNone(order.credited_at)
        self.assertIn("<title>算力星图</title>", checkout_html(self.db, token))
        credits = self.db.query(Ledger).filter(Ledger.ref_payment_order_id == order.id).all()
        self.assertEqual(len(credits), 1)
        self.assertEqual(credits[0].amount, Decimal("0.009980"))

    def test_callback_is_rejected_before_verification_when_legacy_gate_is_off(self):
        output = create_recharge_order(
            self.db,
            self.user.id,
            Decimal("0.01"),
            payment_type="alipay",
        )
        order = self.db.query(PaymentOrder).filter_by(order_no=output["order_no"]).one()
        params = self._paid_params(order)
        settings.MAPAY_LEGACY_RECONCILIATION_ENABLED = False

        with (
            patch("app.services.mapay.verify_params") as verify,
            self.assertRaisesRegex(BizError, "历史收尾尚未启用") as rejected,
        ):
            handle_notification(self.db, params)

        self.assertEqual(rejected.exception.status_code, 503)
        verify.assert_not_called()
        self.db.expire_all()
        unchanged_order = self.db.query(PaymentOrder).filter_by(id=order.id).one()
        unchanged_wallet = self.db.query(Wallet).filter_by(id=self.wallet.id).one()
        self.assertEqual(unchanged_order.status, "pending")
        self.assertIsNone(unchanged_order.credited_at)
        self.assertEqual(unchanged_wallet.balance, Decimal("10.000000"))
        self.assertEqual(
            self.db.query(Ledger).filter_by(ref_payment_order_id=order.id).count(),
            0,
        )

    def test_canceled_order_success_callback_is_preserved_for_manual_review(self):
        output = create_recharge_order(
            self.db,
            self.user.id,
            Decimal("0.01"),
            payment_type="alipay",
        )
        order = self.db.query(PaymentOrder).filter_by(order_no=output["order_no"]).one()
        order.status = "canceled"
        self.db.commit()

        self.assertTrue(handle_notification(self.db, self._paid_params(order)))
        self.db.refresh(order)
        self.db.refresh(self.wallet)
        self.assertEqual(order.status, "review")
        self.assertIsNone(order.credited_at)
        self.assertEqual(self.wallet.balance, Decimal("10.000000"))
        self.assertEqual(
            self.db.query(Ledger).filter_by(ref_payment_order_id=order.id).count(),
            0,
        )

    def test_tampered_amount_or_signature_never_credits_wallet(self):
        output = create_recharge_order(
            self.db,
            self.user.id,
            Decimal("0.01"),
            payment_type="alipay",
        )
        order = self.db.query(PaymentOrder).filter_by(order_no=output["order_no"]).one()
        params = self._paid_params(order, money="1.00")
        with self.assertRaisesRegex(BizError, "金额不匹配"):
            handle_notification(self.db, params)
        self.db.rollback()

        params = self._paid_params(order)
        params["money"] = "0.02"
        with self.assertRaisesRegex(BizError, "签名无效"):
            handle_notification(self.db, params)
        self.db.rollback()
        self.db.refresh(self.wallet)
        self.assertEqual(self.wallet.balance, Decimal("10.0000"))
        self.assertEqual(self.db.query(Ledger).count(), 0)

    def test_missing_or_invalid_channel_never_generates_checkout(self):
        with self.assertRaisesRegex(BizError, "请选择") as missing:
            create_recharge_order(
                self.db,
                self.user.id,
                Decimal("0.01"),
                payment_type=None,
            )
        self.assertEqual(missing.exception.status_code, 400)

        with self.assertRaisesRegex(BizError, "不支持") as invalid:
            create_recharge_order(
                self.db,
                self.user.id,
                Decimal("0.01"),
                payment_type="bank",
            )
        self.assertEqual(invalid.exception.status_code, 400)

        output = create_recharge_order(
            self.db,
            self.user.id,
            Decimal("0.01"),
            payment_type="wxpay",
        )
        order = self.db.query(PaymentOrder).filter_by(order_no=output["order_no"]).one()
        order.channel = None
        self.db.commit()
        token = output["checkout_url"].rsplit("/", 1)[-1]
        with self.assertRaisesRegex(BizError, "请选择") as old_order:
            checkout_html(self.db, token)
        self.assertEqual(old_order.exception.status_code, 400)

    def test_signed_notification_channel_must_match_original_order(self):
        output = create_recharge_order(
            self.db,
            self.user.id,
            Decimal("0.01"),
            payment_type="alipay",
        )
        order = self.db.query(PaymentOrder).filter_by(order_no=output["order_no"]).one()
        params = self._paid_params(order)
        params["type"] = "wxpay"
        params["sign"] = self._platform_sign(params)
        with self.assertRaisesRegex(BizError, "渠道不匹配"):
            handle_notification(self.db, params)
        self.db.rollback()
        self.db.refresh(self.wallet)
        self.db.refresh(order)
        self.assertEqual(self.wallet.balance, Decimal("10.0000"))
        self.assertEqual(order.channel, "alipay")
        self.assertEqual(self.db.query(Ledger).count(), 0)

    def test_status_contract_persists_expiry_and_exposes_server_clock(self):
        output = create_recharge_order(
            self.db,
            self.user.id,
            Decimal("0.01"),
            payment_type="alipay",
        )
        order = self.db.query(PaymentOrder).filter_by(order_no=output["order_no"]).one()
        order.expires_at = utc_now() - timedelta(seconds=1)
        self.db.commit()

        status = payment_status(self.db, self.user.id, order.order_no)
        self.db.refresh(order)
        self.assertEqual(status["status"], "expired")
        self.assertEqual(status["remaining_seconds"], 0)
        self.assertTrue(status["is_expired"])
        self.assertFalse(status["can_pay"])
        self.assertTrue(status["can_query"])
        self.assertTrue(status["server_time"].endswith("Z"))
        self.assertTrue(status["created_at"].endswith("Z"))
        self.assertTrue(status["expires_at"].endswith("Z"))
        self.assertIn("支付时限", status["failure_reason"])
        self.assertEqual(order.status, "expired")

    def test_expiry_sweeper_is_idempotent(self):
        for seconds in (-2, -1, 60):
            output = create_recharge_order(
                self.db,
                self.user.id,
                Decimal("0.01"),
                payment_type="alipay",
            )
            order = self.db.query(PaymentOrder).filter_by(order_no=output["order_no"]).one()
            order.expires_at = utc_now() + timedelta(seconds=seconds)
        self.db.commit()
        self.assertEqual(expire_pending_payment_orders(self.db), 2)
        self.db.commit()
        self.assertEqual(expire_pending_payment_orders(self.db), 0)

    def test_timely_provider_endtime_credits_after_delayed_callback(self):
        output = create_recharge_order(
            self.db,
            self.user.id,
            Decimal("0.01"),
            payment_type="alipay",
        )
        order = self.db.query(PaymentOrder).filter_by(order_no=output["order_no"]).one()
        order.expires_at = utc_now() - timedelta(seconds=30)
        paid_at = order.expires_at - timedelta(seconds=10)
        self.db.commit()
        params = self._paid_params(order)
        params["endtime"] = self._provider_local_time(paid_at)
        params["sign"] = self._platform_sign(params)

        self.assertTrue(handle_notification(self.db, params))
        self.db.refresh(order)
        self.db.refresh(self.wallet)
        self.assertEqual(order.status, "paid")
        self.assertLessEqual(order.paid_at, order.expires_at)
        self.assertEqual(self.wallet.balance, Decimal("10.009980"))
        self.assertEqual(self.db.query(Ledger).count(), 1)

    def test_payment_completed_after_deadline_requires_review_and_never_credits(self):
        output = create_recharge_order(
            self.db,
            self.user.id,
            Decimal("0.01"),
            payment_type="alipay",
        )
        order = self.db.query(PaymentOrder).filter_by(order_no=output["order_no"]).one()
        order.expires_at = utc_now() - timedelta(seconds=30)
        late_paid_at = order.expires_at + timedelta(seconds=5)
        self.db.commit()
        params = self._paid_params(order)
        params["endtime"] = self._provider_local_time(late_paid_at)
        params["sign"] = self._platform_sign(params)

        self.assertTrue(handle_notification(self.db, params))
        self.assertTrue(handle_notification(self.db, params))
        self.db.refresh(order)
        self.db.refresh(self.wallet)
        self.assertEqual(order.status, "late_paid_review")
        self.assertIn("晚于", order.failure_reason)
        self.assertIsNone(order.credited_at)
        self.assertEqual(self.wallet.balance, Decimal("10.000000"))
        self.assertEqual(self.db.query(Ledger).count(), 0)

    def test_failure_redelivery_cannot_remove_success_from_review_queue(self):
        output = create_recharge_order(
            self.db,
            self.user.id,
            Decimal("0.01"),
            payment_type="alipay",
        )
        order = self.db.query(PaymentOrder).filter_by(order_no=output["order_no"]).one()
        order.expires_at = utc_now() - timedelta(seconds=30)
        paid_at = order.expires_at + timedelta(seconds=5)
        self.db.commit()
        success = self._paid_params(order)
        success["endtime"] = self._provider_local_time(paid_at)
        success["sign"] = self._platform_sign(success)
        self.assertTrue(handle_notification(self.db, success))
        self.db.refresh(order)
        self.assertEqual(order.status, "late_paid_review")

        failure = self._paid_params(order)
        failure["trade_status"] = "TRADE_FAILED"
        failure["sign"] = self._platform_sign(failure)
        self.assertFalse(handle_notification(self.db, failure))
        self.db.refresh(order)
        self.db.refresh(self.wallet)
        self.assertEqual(order.status, "late_paid_review")
        self.assertEqual(order.provider_status, "TRADE_SUCCESS")
        self.assertIsNone(order.credited_at)
        self.assertEqual(self.wallet.balance, Decimal("10.000000"))

    def test_late_success_without_trusted_time_enters_review_when_query_unavailable(self):
        output = create_recharge_order(
            self.db,
            self.user.id,
            Decimal("0.01"),
            payment_type="alipay",
        )
        order = self.db.query(PaymentOrder).filter_by(order_no=output["order_no"]).one()
        order.expires_at = utc_now() - timedelta(seconds=1)
        self.db.commit()
        params = self._paid_params(order)

        with patch(
            "app.services.mapay._query_provider_payload",
            side_effect=BizError("provider unavailable", status_code=502),
        ):
            self.assertTrue(handle_notification(self.db, params))
        self.db.refresh(order)
        self.db.refresh(self.wallet)
        self.assertEqual(order.status, "review")
        self.assertIsNone(order.credited_at)
        self.assertEqual(self.wallet.balance, Decimal("10.000000"))

    def test_late_callback_uses_signed_query_endtime_to_credit_timely_payment(self):
        output = create_recharge_order(
            self.db,
            self.user.id,
            Decimal("0.01"),
            payment_type="alipay",
        )
        order = self.db.query(PaymentOrder).filter_by(order_no=output["order_no"]).one()
        order.expires_at = utc_now() - timedelta(seconds=30)
        self.db.commit()
        callback = self._paid_params(order)
        queried = {
            "code": 0,
            "status": 1,
            "pid": "10001",
            "trade_no": "MAPAY-TEST-0001",
            "out_trade_no": order.order_no,
            "type": "alipay",
            "money": "0.01",
            "endtime": self._provider_local_time(order.expires_at - timedelta(seconds=5)),
        }
        with patch("app.services.mapay._query_provider_payload", return_value=queried) as query:
            self.assertTrue(handle_notification(self.db, callback))
        query.assert_called_once()
        self.db.refresh(order)
        self.db.refresh(self.wallet)
        self.assertEqual(order.status, "paid")
        self.assertEqual(self.wallet.balance, Decimal("10.009980"))

    def test_query_success_without_paid_time_after_deadline_requires_review(self):
        output = create_recharge_order(
            self.db,
            self.user.id,
            Decimal("0.01"),
            payment_type="alipay",
        )
        order = self.db.query(PaymentOrder).filter_by(order_no=output["order_no"]).one()
        order.expires_at = utc_now() - timedelta(seconds=1)
        self.db.commit()
        queried = {
            "code": 0,
            "status": 1,
            "pid": "10001",
            "trade_no": "MAPAY-QUERY-NOTIME-0001",
            "out_trade_no": order.order_no,
            "type": "alipay",
            "money": "0.01",
        }
        with patch("app.services.mapay._query_provider_payload", return_value=queried):
            result = query_provider_and_reconcile(self.db, order)
        self.assertEqual(result["status"], "review")
        self.assertIn("可信支付完成时间", result["failure_reason"])
        self.db.refresh(self.wallet)
        self.assertEqual(self.wallet.balance, Decimal("10.000000"))
        self.assertEqual(self.db.query(Ledger).count(), 0)

    def test_active_query_reconciles_once_in_card_hours(self):
        output = create_recharge_order(
            self.db,
            self.user.id,
            Decimal("0.01"),
            payment_type="alipay",
        )
        order = self.db.query(PaymentOrder).filter_by(order_no=output["order_no"]).one()
        payload = {
            "code": 0,
            "status": 1,
            "pid": "10001",
            "trade_no": "MAPAY-QUERY-PAID-0001",
            "out_trade_no": order.order_no,
            "type": "alipay",
            "money": "0.01",
        }
        with patch("app.services.mapay._query_provider_payload", return_value=payload) as query:
            first = query_provider_and_reconcile(self.db, order)
            second = query_provider_and_reconcile(self.db, order)
        self.assertEqual(query.call_count, 1)
        self.assertEqual(first["status"], "paid")
        self.assertEqual(second["status"], "paid")
        self.db.refresh(self.wallet)
        self.assertEqual(self.wallet.balance, Decimal("10.009980"))
        credits = self.db.query(Ledger).filter_by(ref_payment_order_id=order.id).all()
        self.assertEqual(len(credits), 1)
        self.assertEqual(credits[0].amount, Decimal("0.009980"))

    def test_precision_migration_repairs_legacy_cny_credit_once(self):
        from init_db import _migrate_payment_precision_and_pending_deadlines

        output = create_recharge_order(
            self.db,
            self.user.id,
            Decimal("0.01"),
            payment_type="alipay",
        )
        order = self.db.query(PaymentOrder).filter_by(order_no=output["order_no"]).one()
        order.status = "paid"
        order.paid_at = utc_now()
        order.credited_at = utc_now()
        self.wallet.balance = Decimal("10.010000")
        self.db.add(Ledger(
            user_id=self.user.id,
            wallet_id=self.wallet.id,
            type="recharge",
            direction="in",
            amount=Decimal("0.010000"),
            balance_after=Decimal("10.010000"),
            ref_payment_order_id=order.id,
        ))
        self.db.commit()

        first = _migrate_payment_precision_and_pending_deadlines(
            self.engine,
            self.db,
        )
        self.db.expire_all()
        self.assertEqual(first["corrected_credits"], 1)
        self.assertEqual(
            self.db.query(Wallet).filter_by(id=self.wallet.id).one().balance,
            Decimal("10.009980"),
        )
        credit = self.db.query(Ledger).filter_by(ref_payment_order_id=order.id).one()
        self.assertEqual(credit.amount, Decimal("0.009980"))
        self.assertEqual(credit.balance_after, Decimal("10.009980"))

        second = _migrate_payment_precision_and_pending_deadlines(
            self.engine,
            self.db,
        )
        self.assertEqual(second["corrected_credits"], 0)

    def test_precision_migration_marker_and_money_repair_are_concurrency_safe(self):
        from init_db import _migrate_payment_precision_and_pending_deadlines

        database = Path(self.tempdir.name) / "precision-concurrency.db"
        engine = create_engine(
            f"sqlite:///{database}",
            connect_args={"check_same_thread": False, "timeout": 10},
        )
        Base.metadata.create_all(engine)
        Session = sessionmaker(bind=engine, expire_on_commit=False)
        setup = Session()
        user = User(phone="13900000999", username="迁移并发用户", password="!")
        setup.add(user)
        setup.flush()
        wallet = Wallet(user_id=user.id, balance=Decimal("9.010000"), frozen=Decimal("0"))
        setup.add(wallet)
        setup.flush()
        now = utc_now()
        order = PaymentOrder(
            order_no="PAY-PRECISION-CONCURRENT-1",
            user_id=user.id,
            provider="mapay",
            status="paid",
            amount_cny=Decimal("0.01"),
            card_hours=Decimal("0.009980"),
            card_hour_rate=Decimal("1.002000"),
            checkout_token_hash="precision-concurrent-token",
            expires_at=now + timedelta(minutes=5),
            paid_at=now,
            credited_at=now,
            created_at=now,
        )
        setup.add(order)
        setup.flush()
        setup.add_all([
            Ledger(
                user_id=user.id, wallet_id=wallet.id, type="recharge", direction="in",
                amount=Decimal("0.010000"), balance_after=Decimal("10.010000"),
                ref_payment_order_id=order.id,
            ),
            Ledger(
                user_id=user.id, wallet_id=wallet.id, type="pay", direction="out",
                amount=Decimal("1.000000"), balance_after=Decimal("9.010000"),
            ),
        ])
        setup.commit()
        setup.close()

        barrier = threading.Barrier(2)

        def migrate_once():
            db = Session()
            try:
                barrier.wait(timeout=5)
                return _migrate_payment_precision_and_pending_deadlines(engine, db)
            finally:
                db.close()

        with ThreadPoolExecutor(max_workers=2) as pool:
            results = list(pool.map(lambda _: migrate_once(), range(2)))

        self.assertEqual(sorted(item["corrected_credits"] for item in results), [0, 1])
        check = Session()
        final_wallet = check.query(Wallet).filter_by(user_id=user.id).one()
        self.assertEqual(final_wallet.balance, Decimal("9.009980"))
        ledgers = check.query(Ledger).order_by(Ledger.id.asc()).all()
        self.assertEqual(ledgers[0].amount, Decimal("0.009980"))
        self.assertEqual(ledgers[0].balance_after, Decimal("10.009980"))
        self.assertEqual(ledgers[1].balance_after, Decimal("9.009980"))
        marker_count = check.execute(text(
            "SELECT COUNT(*) FROM app_migrations "
            "WHERE name = '20260820_payment_card_hour_precision_v1'"
        )).scalar_one()
        self.assertEqual(marker_count, 1)
        check.close()
        engine.dispose()

    def test_provider_stays_disabled_without_both_key_files(self):
        settings.MAPAY_PLATFORM_PUBLIC_KEY_PATH = ""
        self.assertFalse(provider_configured())
        with self.assertRaisesRegex(BizError, "密钥配置"):
            create_recharge_order(
                self.db,
                self.user.id,
                Decimal("0.01"),
                payment_type="alipay",
            )

    def test_legacy_reconciliation_readiness_fails_closed_per_required_setting(self):
        settings.PAYMENT_SERVICE_ENABLED = False
        settings.MAPAY_ENABLED = False
        settings.MAPAY_LEGACY_RECONCILIATION_ENABLED = True

        self.assertTrue(legacy_reconciliation_configured())
        self.assertFalse(
            any(error.startswith("mapay_") for error in payment_readiness_errors())
        )
        assert_payment_configuration_safe()

        cases = (
            ("MAPAY_PID", "", "mapay_pid_missing"),
            (
                "MAPAY_BASE_URL",
                "https://attacker.example/xpay/epayn",
                "mapay_base_url_invalid",
            ),
            (
                "MAPAY_MERCHANT_PRIVATE_KEY_PATH",
                str(Path(self.tempdir.name) / "missing-private.pem"),
                "mapay_merchant_private_key_invalid",
            ),
            (
                "MAPAY_PLATFORM_PUBLIC_KEY_PATH",
                str(Path(self.tempdir.name) / "missing-public.pem"),
                "mapay_platform_public_key_invalid",
            ),
            ("MAPAY_PROVIDER_TIMEZONE", "Mars/Olympus", "mapay_timezone_invalid"),
            ("MAPAY_HTTP_TIMEOUT", 0, "mapay_http_timeout_invalid"),
            ("MAPAY_HTTP_TIMEOUT", 56, "mapay_http_timeout_invalid"),
            ("MAPAY_HTTP_TIMEOUT", float("nan"), "mapay_http_timeout_invalid"),
        )
        for name, unsafe_value, expected_error in cases:
            original = getattr(settings, name)
            setattr(settings, name, unsafe_value)
            with self.subTest(name=name, value=unsafe_value):
                self.assertIn(expected_error, payment_readiness_errors())
                self.assertFalse(legacy_reconciliation_configured())
                with self.assertRaisesRegex(RuntimeError, expected_error):
                    assert_payment_configuration_safe()
            setattr(settings, name, original)

    def test_legacy_query_rejects_nonofficial_base_before_signing_or_network(self):
        output = create_recharge_order(
            self.db,
            self.user.id,
            Decimal("0.01"),
            payment_type="alipay",
        )
        order = self.db.query(PaymentOrder).filter_by(order_no=output["order_no"]).one()
        settings.PAYMENT_SERVICE_ENABLED = False
        settings.MAPAY_ENABLED = False
        settings.MAPAY_BASE_URL = "https://attacker.example/xpay/epayn"

        with (
            patch("app.services.mapay.sign_params") as sign,
            patch("app.services.mapay.httpx.post") as post,
            self.assertRaisesRegex(BizError, "历史查询地址配置无效") as rejected,
        ):
            query_provider_and_reconcile(self.db, order)

        self.assertEqual(rejected.exception.status_code, 503)
        sign.assert_not_called()
        post.assert_not_called()


if __name__ == "__main__":
    unittest.main()
