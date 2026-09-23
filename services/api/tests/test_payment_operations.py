import json
import tempfile
import unittest
from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta
from decimal import Decimal
from pathlib import Path
from unittest.mock import patch

from sqlalchemy import create_engine, inspect, text
from sqlalchemy.orm import Query, sessionmaker

from app.core.config import settings
from app.db.base import Base
from app.models import Ledger, PaymentEvent, PaymentOrder, PaymentRefund, User, Wallet
from app.services.payment_gateway import assert_payment_configuration_safe
from app.services.payment_operations import (
    recover_stale_refund_submissions,
    request_payment_refund,
    resolve_payment_review,
    resolve_unknown_refund,
)
from app.services.payment_reconciliation import reconcile_payment_orders
from app.services.qixiangpay import (
    ProviderRefundUncertain,
    credit_verified_payment,
    create_recharge_order,
    handle_notification,
    query_provider_and_reconcile,
    sign_params,
)
from app.utils.response import BizError
import init_db


class FakeResponse:
    def __init__(self, payload: dict):
        self.content = json.dumps(payload).encode("utf-8")

    def raise_for_status(self):
        return None


class PaymentOperationsTests(unittest.TestCase):
    def setUp(self):
        self.tempdir = tempfile.TemporaryDirectory()
        database_path = Path(self.tempdir.name) / "payments.db"
        self.engine = create_engine(
            f"sqlite:///{database_path.as_posix()}",
            connect_args={"check_same_thread": False, "timeout": 30},
        )
        Base.metadata.create_all(self.engine)
        self.Session = sessionmaker(bind=self.engine, expire_on_commit=False)
        self.db = self.Session()
        self.user = User(phone="13900002901", username="支付操作用户", password="!")
        self.admin = User(
            phone="13900002902", username="支付操作管理员", password="!", role="admin"
        )
        self.reviewer = User(
            phone="13900002903", username="支付复核管理员", password="!", role="admin"
        )
        self.db.add_all([self.user, self.admin, self.reviewer])
        self.db.flush()
        self.wallet = Wallet(
            user_id=self.user.id,
            balance=Decimal("0"),
            frozen=Decimal("0"),
            promotional_balance=Decimal("0"),
            promotional_frozen=Decimal("0"),
            withdrawable_balance=Decimal("0"),
            withdraw_frozen=Decimal("0"),
        )
        self.db.add(self.wallet)
        self.db.commit()
        self.user_id = self.user.id
        self.admin_id = self.admin.id
        self.reviewer_id = self.reviewer.id

        names = (
            "SECRET_KEY",
            "DIRECT_TRADE_ENABLED",
            "PAYMENT_SERVICE_ENABLED",
            "MAPAY_ENABLED",
            "MAPAY_LEGACY_RECONCILIATION_ENABLED",
            "QIXIANGPAY_ENABLED",
            "QIXIANGPAY_REFUND_ENABLED",
            "QIXIANGPAY_BASE_URL",
            "QIXIANGPAY_PID",
            "QIXIANGPAY_KEY",
            "QIXIANGPAY_NOTIFY_URL",
            "QIXIANGPAY_RETURN_URL",
            "QIXIANGPAY_PUBLIC_API_BASE_URL",
            "QIXIANGPAY_PAYMENT_TYPES",
            "PAYMENT_CHECKOUT_ALLOWED_HOSTS",
            "QIXIANGPAY_MIN_AMOUNT_CNY",
            "QIXIANGPAY_MAX_AMOUNT_CNY",
            "CARD_HOUR_RMB_RATE",
            "PAYMENT_MAX_PENDING_ORDERS_PER_USER",
            "PAYMENT_DAILY_RECHARGE_LIMIT_CNY",
            "PAYMENT_RECONCILIATION_ENABLED",
            "PAYMENT_RECONCILIATION_BATCH_SIZE",
            "PAYMENT_RECONCILIATION_MIN_AGE_SECONDS",
            "PAYMENT_RECONCILIATION_MAX_AGE_SECONDS",
        )
        self.original = {name: getattr(settings, name) for name in names}
        settings.SECRET_KEY = "unit-test-payment-operations-secret"
        settings.DIRECT_TRADE_ENABLED = True
        settings.PAYMENT_SERVICE_ENABLED = True
        settings.MAPAY_ENABLED = False
        settings.MAPAY_LEGACY_RECONCILIATION_ENABLED = False
        settings.QIXIANGPAY_ENABLED = True
        settings.QIXIANGPAY_REFUND_ENABLED = True
        settings.QIXIANGPAY_BASE_URL = "https://api.payqixiang.cn"
        settings.QIXIANGPAY_PID = "test-pid"
        settings.QIXIANGPAY_KEY = "unit-test-provider-key"
        settings.QIXIANGPAY_NOTIFY_URL = "https://wod.kai.com/api/payments/qixiang/notify"
        settings.QIXIANGPAY_RETURN_URL = "https://wod.kai.com/payment/qixiang/return"
        settings.QIXIANGPAY_PUBLIC_API_BASE_URL = "https://wod.kai.com/api"
        settings.QIXIANGPAY_PAYMENT_TYPES = "alipay,wxpay"
        settings.PAYMENT_CHECKOUT_ALLOWED_HOSTS = "api.example.test"
        settings.QIXIANGPAY_MIN_AMOUNT_CNY = 0.01
        settings.QIXIANGPAY_MAX_AMOUNT_CNY = 50000
        settings.CARD_HOUR_RMB_RATE = 1.002
        settings.PAYMENT_MAX_PENDING_ORDERS_PER_USER = 5
        settings.PAYMENT_DAILY_RECHARGE_LIMIT_CNY = 50000
        settings.PAYMENT_RECONCILIATION_ENABLED = False
        settings.PAYMENT_RECONCILIATION_BATCH_SIZE = 20
        settings.PAYMENT_RECONCILIATION_MIN_AGE_SECONDS = 30
        settings.PAYMENT_RECONCILIATION_MAX_AGE_SECONDS = 86400

    def tearDown(self):
        for name, value in self.original.items():
            setattr(settings, name, value)
        self.db.close()
        self.engine.dispose()
        self.tempdir.cleanup()

    def _new_order(
        self,
        *,
        request_id: str | None = None,
        amount_cny: Decimal = Decimal("10.02"),
    ) -> PaymentOrder:
        output = create_recharge_order(
            self.db,
            self.user_id,
            amount_cny,
            payment_type="alipay",
            client_request_id=request_id,
        )
        return self.db.query(PaymentOrder).filter_by(order_no=output["order_no"]).one()

    def _mark_paid(self, order: PaymentOrder) -> Decimal:
        amount = Decimal(order.card_hours).quantize(Decimal("0.000001"))
        order.status = "paid"
        order.provider_status = "TRADE_SUCCESS"
        order.provider_trade_no = f"QX-{order.order_no}"
        order.paid_at = order.created_at
        order.credited_at = order.created_at
        self.wallet.balance = amount
        self.db.commit()
        return amount

    @staticmethod
    def _success_callback(order: PaymentOrder) -> dict:
        params = {
            "pid": settings.QIXIANGPAY_PID,
            "trade_no": order.provider_trade_no or f"QX-{order.order_no}",
            "out_trade_no": order.order_no,
            "type": order.channel,
            "name": "KAI钱包卡时充值",
            "money": f"{order.amount_cny:.2f}",
            "trade_status": "TRADE_SUCCESS",
            "param": order.order_no,
            "sign_type": "MD5",
        }
        params["sign"] = sign_params(params)
        return params

    @staticmethod
    def _query_response(order: PaymentOrder, *, status: int = 0) -> FakeResponse:
        return FakeResponse({
            "code": 1,
            "msg": "ok",
            "trade_no": order.provider_trade_no or f"QX-{order.order_no}",
            "out_trade_no": order.order_no,
            "type": order.channel,
            "pid": settings.QIXIANGPAY_PID,
            "money": f"{order.amount_cny:.2f}",
            "status": status,
            "param": order.order_no,
        })

    def test_recharge_creation_is_idempotent_and_replays_checkout_url(self):
        request_id = "recharge-11111111-1111-4111-8111-111111111111"
        first = create_recharge_order(
            self.db,
            self.user_id,
            Decimal("10.02"),
            payment_type="alipay",
            client_request_id=request_id,
        )
        second = create_recharge_order(
            self.db,
            self.user_id,
            Decimal("10.02"),
            payment_type="alipay",
            client_request_id=request_id,
        )
        self.assertEqual(first["order_no"], second["order_no"])
        self.assertEqual(first["checkout_url"], second["checkout_url"])
        self.assertEqual(self.db.query(PaymentOrder).count(), 1)
        self.assertEqual(self.db.query(PaymentEvent).count(), 1)

        with self.assertRaisesRegex(BizError, "幂等键") as conflict:
            create_recharge_order(
                self.db,
                self.user_id,
                Decimal("20.04"),
                payment_type="alipay",
                client_request_id=request_id,
            )
        self.assertEqual(conflict.exception.status_code, 409)

    def test_review_credit_reuses_verified_credit_and_records_safe_event(self):
        order = self._new_order()
        order.status = "review"
        order.provider_status = "TRADE_SUCCESS"
        order.provider_trade_no = f"QX-{order.order_no}"
        self.db.commit()
        payload = {
            "code": 1,
            "pid": settings.QIXIANGPAY_PID,
            "trade_no": order.provider_trade_no,
            "out_trade_no": order.order_no,
            "type": order.channel,
            "money": f"{order.amount_cny:.2f}",
            "status": 1,
            "param": order.order_no,
        }
        with patch("app.services.qixiangpay._query_provider_payload", return_value=payload):
            result = resolve_payment_review(
                self.db,
                payment_order_id=order.id,
                actor_user_id=self.admin_id,
                action="credit",
                note="已核对七相商户后台与支付时间",
            )
        self.assertTrue(result["credited"])
        self.db.refresh(self.wallet)
        self.assertEqual(self.wallet.balance, order.card_hours)
        event = self.db.query(PaymentEvent).filter_by(
            payment_order_id=order.id,
            event_type="payment_credited_after_review",
        ).one()
        self.assertEqual(event.detail["card_hours"], str(order.card_hours))
        self.assertNotIn("sign", event.detail)

    def test_successful_refund_holds_before_io_then_settles_once(self):
        order = self._new_order()
        amount = self._mark_paid(order)

        def provider_success(_order):
            check = self.Session()
            try:
                wallet = check.query(Wallet).filter_by(user_id=self.user_id).one()
                self.assertEqual(wallet.balance, Decimal("0.000000"))
                self.assertEqual(wallet.frozen, amount)
            finally:
                check.close()
            return {"success": True, "code": "1", "msg": "退款成功"}

        with patch(
            "app.services.qixiangpay.submit_provider_refund",
            side_effect=provider_success,
        ) as submit:
            result = request_payment_refund(
                self.db,
                payment_order_id=order.id,
                actor_user_id=self.admin_id,
                client_request_id="refund-11111111-1111-4111-8111-111111111111",
                reason="用户申请原路全额退款",
            )
            replay = request_payment_refund(
                self.db,
                payment_order_id=order.id,
                actor_user_id=self.admin_id,
                client_request_id="refund-11111111-1111-4111-8111-111111111111",
                reason="用户申请原路全额退款",
            )
        self.assertEqual(result["status"], "succeeded")
        self.assertEqual(replay["refund_no"], result["refund_no"])
        submit.assert_called_once()
        self.db.expire_all()
        wallet = self.db.query(Wallet).filter_by(user_id=self.user_id).one()
        self.assertEqual(wallet.balance, Decimal("0.000000"))
        self.assertEqual(wallet.frozen, Decimal("0.000000"))
        self.assertEqual(
            self.db.query(Ledger).filter(Ledger.ref_payment_refund_id.isnot(None)).count(),
            1,
        )
        self.assertEqual(self.db.get(PaymentOrder, order.id).status, "refunded")

    def test_uncertain_refund_stays_held_until_admin_marks_failed(self):
        order = self._new_order()
        amount = self._mark_paid(order)
        with patch(
            "app.services.qixiangpay.submit_provider_refund",
            side_effect=ProviderRefundUncertain("timeout", status_code=502),
        ) as submit:
            result = request_payment_refund(
                self.db,
                payment_order_id=order.id,
                actor_user_id=self.admin_id,
                client_request_id="refund-22222222-2222-4222-8222-222222222222",
                reason="用户申请原路全额退款",
            )
            replay = request_payment_refund(
                self.db,
                payment_order_id=order.id,
                actor_user_id=self.admin_id,
                client_request_id="refund-22222222-2222-4222-8222-222222222222",
                reason="用户申请原路全额退款",
            )
        self.assertEqual(result["status"], "unknown")
        self.assertEqual(replay["status"], "unknown")
        submit.assert_called_once()
        self.db.expire_all()
        wallet = self.db.query(Wallet).filter_by(user_id=self.user_id).one()
        self.assertEqual(wallet.balance, Decimal("0.000000"))
        self.assertEqual(wallet.frozen, amount)

        with self.assertRaisesRegex(BizError, "另一名管理员") as self_review:
            resolve_unknown_refund(
                self.db,
                refund_id=result["id"],
                actor_user_id=self.admin_id,
                outcome="failed",
                note="原操作人不能自行解除冻结",
            )
        self.assertEqual(self_review.exception.status_code, 409)
        self.db.rollback()

        resolved = resolve_unknown_refund(
            self.db,
            refund_id=result["id"],
            actor_user_id=self.reviewer_id,
            outcome="failed",
            note="已在七相商户后台核对，未产生退款",
        )
        self.assertEqual(resolved["status"], "failed")
        self.db.expire_all()
        wallet = self.db.query(Wallet).filter_by(user_id=self.user_id).one()
        self.assertEqual(wallet.balance, amount)
        self.assertEqual(wallet.frozen, Decimal("0.000000"))
        self.assertEqual(self.db.get(PaymentOrder, order.id).status, "paid")

    def test_structurally_invalid_refund_json_is_unknown_and_keeps_hold(self):
        order = self._new_order()
        amount = self._mark_paid(order)
        with patch(
            "app.services.qixiangpay.httpx.post",
            return_value=FakeResponse({"msg": "upstream error envelope"}),
        ):
            result = request_payment_refund(
                self.db,
                payment_order_id=order.id,
                actor_user_id=self.admin_id,
                client_request_id="refund-invalid-json-envelope-0001",
                reason="异常响应不得释放退款冻结",
            )
        self.assertEqual(result["status"], "unknown")
        self.db.expire_all()
        wallet = self.db.get(Wallet, self.wallet.id)
        self.assertEqual(wallet.balance, Decimal("0.000000"))
        self.assertEqual(wallet.frozen, amount)
        self.assertEqual(self.db.get(PaymentOrder, order.id).status, "refund_unknown")

    def test_disabled_refund_fails_before_wallet_hold(self):
        order = self._new_order()
        amount = self._mark_paid(order)
        settings.QIXIANGPAY_REFUND_ENABLED = False
        with patch("app.services.qixiangpay.httpx.post") as post:
            with self.assertRaisesRegex(BizError, "退款能力") as disabled:
                request_payment_refund(
                    self.db,
                    payment_order_id=order.id,
                    actor_user_id=self.admin_id,
                    client_request_id="refund-33333333-3333-4333-8333-333333333333",
                    reason="用户申请原路全额退款",
                )
        self.assertEqual(disabled.exception.status_code, 503)
        post.assert_not_called()
        self.db.expire_all()
        wallet = self.db.query(Wallet).filter_by(user_id=self.user_id).one()
        self.assertEqual(wallet.balance, amount)
        self.assertEqual(wallet.frozen, Decimal("0.000000"))
        self.assertEqual(self.db.query(PaymentRefund).count(), 0)

    def test_definitive_provider_failure_releases_hold_and_can_retry(self):
        order = self._new_order()
        amount = self._mark_paid(order)
        request_id = "refund-66666666-6666-4666-8666-666666666666"
        with patch(
            "app.services.qixiangpay.submit_provider_refund",
            return_value={"success": False, "code": "-1", "msg": "余额不足"},
        ) as submit:
            failed = request_payment_refund(
                self.db,
                payment_order_id=order.id,
                actor_user_id=self.admin_id,
                client_request_id=request_id,
                reason="用户申请原路全额退款",
            )
        self.assertEqual(failed["status"], "failed")
        self.db.expire_all()
        wallet = self.db.query(Wallet).filter_by(user_id=self.user_id).one()
        self.assertEqual(wallet.balance, amount)
        self.assertEqual(wallet.frozen, Decimal("0.000000"))

        with patch(
            "app.services.qixiangpay.submit_provider_refund",
            return_value={"success": True, "code": "0", "msg": "退款成功"},
        ) as retry:
            succeeded = request_payment_refund(
                self.db,
                payment_order_id=order.id,
                actor_user_id=self.admin_id,
                client_request_id=request_id,
                reason="商户余额补足后重试",
            )
        self.assertEqual(succeeded["status"], "succeeded")
        submit.assert_called_once()
        retry.assert_called_once()
        self.db.expire_all()
        wallet = self.db.query(Wallet).filter_by(user_id=self.user_id).one()
        self.assertEqual(wallet.balance, Decimal("0.000000"))
        self.assertEqual(wallet.frozen, Decimal("0.000000"))

    def test_failed_refund_retry_restores_current_post_review_paid_state(self):
        order = self._new_order()
        order.status = "review"
        order.provider_status = "TRADE_SUCCESS"
        order.provider_trade_no = f"QX-{order.order_no}"
        self.db.commit()
        request_id = "refund-review-retry-0001"

        with patch(
            "app.services.qixiangpay.submit_provider_refund",
            return_value={"success": False, "code": "-1", "msg": "商户余额不足"},
        ):
            first = request_payment_refund(
                self.db,
                payment_order_id=order.id,
                actor_user_id=self.admin_id,
                client_request_id=request_id,
                reason="复核单首次退款",
            )
        self.assertEqual(first["status"], "failed")
        self.assertEqual(first["previous_payment_status"], "review")

        payload = json.loads(self._query_response(order, status=1).content)
        with patch("app.services.qixiangpay._query_provider_payload", return_value=payload):
            credited = resolve_payment_review(
                self.db,
                payment_order_id=order.id,
                actor_user_id=self.admin_id,
                action="credit",
                note="退款拒绝后复核入账",
            )
        self.assertTrue(credited["credited"])

        with patch(
            "app.services.qixiangpay.submit_provider_refund",
            return_value={"success": False, "code": "-1", "msg": "仍无法退款"},
        ):
            retried = request_payment_refund(
                self.db,
                payment_order_id=order.id,
                actor_user_id=self.admin_id,
                client_request_id=request_id,
                reason="入账后再次退款",
            )
        self.assertEqual(retried["status"], "failed")
        self.assertEqual(retried["previous_payment_status"], "paid")
        self.db.expire_all()
        current = self.db.get(PaymentOrder, order.id)
        wallet = self.db.get(Wallet, self.wallet.id)
        self.assertEqual(current.status, "paid")
        self.assertIsNotNone(current.credited_at)
        self.assertEqual(wallet.balance, order.card_hours)
        self.assertEqual(wallet.frozen, Decimal("0.000000"))

    def test_promotional_or_consumed_balance_is_never_refunded_as_cash(self):
        order = self._new_order()
        amount = self._mark_paid(order)
        self.wallet.promotional_balance = amount
        self.db.commit()
        with patch("app.services.qixiangpay.submit_provider_refund") as submit:
            with self.assertRaisesRegex(BizError, "转人工") as insufficient:
                request_payment_refund(
                    self.db,
                    payment_order_id=order.id,
                    actor_user_id=self.admin_id,
                    client_request_id="refund-44444444-4444-4444-8444-444444444444",
                    reason="用户申请原路全额退款",
                )
        self.assertEqual(insufficient.exception.status_code, 409)
        submit.assert_not_called()

    def test_concurrent_refund_requests_aggregate_one_wallet_hold(self):
        order = self._new_order()
        amount = self._mark_paid(order)
        request_id = "refund-55555555-5555-4555-8555-555555555555"

        def worker():
            session = self.Session()
            try:
                return request_payment_refund(
                    session,
                    payment_order_id=order.id,
                    actor_user_id=self.admin_id,
                    client_request_id=request_id,
                    reason="并发幂等退款测试",
                )
            finally:
                session.close()

        with patch(
            "app.services.qixiangpay.submit_provider_refund",
            side_effect=ProviderRefundUncertain("timeout", status_code=502),
        ) as submit:
            with ThreadPoolExecutor(max_workers=2) as pool:
                results = list(pool.map(lambda _index: worker(), range(2)))
        self.assertEqual({row["status"] for row in results}, {"unknown"})
        submit.assert_called_once()
        self.db.expire_all()
        wallet = self.db.query(Wallet).filter_by(user_id=self.user_id).one()
        self.assertEqual(wallet.balance, Decimal("0.000000"))
        self.assertEqual(wallet.frozen, amount)
        self.assertEqual(self.db.query(PaymentRefund).count(), 1)
        self.assertEqual(
            self.db.query(Ledger).filter(Ledger.ref_payment_refund_id.isnot(None)).count(),
            0,
        )

    def test_provider_configuration_rejects_mapay_new_collection(self):
        settings.QIXIANGPAY_ENABLED = False
        settings.QIXIANGPAY_REFUND_ENABLED = False
        settings.MAPAY_ENABLED = True
        with self.assertRaisesRegex(RuntimeError, "mapay_new_collection_retired"):
            assert_payment_configuration_safe()

    def test_collection_readiness_pins_all_payment_origins_and_checkout_hosts(self):
        cases = (
            (
                "QIXIANGPAY_BASE_URL",
                "https://gateway.example.test",
                "qixiangpay_base_url_invalid",
            ),
            (
                "QIXIANGPAY_NOTIFY_URL",
                "https://example.test/api/payments/qixiang/notify",
                "qixiangpay_notify_url_invalid",
            ),
            (
                "QIXIANGPAY_RETURN_URL",
                "https://example.test/payment/qixiang/return",
                "qixiangpay_return_url_invalid",
            ),
            (
                "QIXIANGPAY_PUBLIC_API_BASE_URL",
                "https://example.test/api",
                "qixiangpay_public_api_base_url_invalid",
            ),
        )
        for name, unsafe_value, expected_error in cases:
            original = getattr(settings, name)
            setattr(settings, name, unsafe_value)
            with self.subTest(name=name):
                with self.assertRaisesRegex(RuntimeError, expected_error):
                    assert_payment_configuration_safe()
            setattr(settings, name, original)

        settings.QIXIANGPAY_RETURN_URL = "https://wod.kai.com/account/wallet"
        with self.assertRaisesRegex(RuntimeError, "qixiangpay_return_url_invalid"):
            assert_payment_configuration_safe()

        settings.QIXIANGPAY_RETURN_URL = "https://wod.kai.com/payment/qixiang/return"
        settings.PAYMENT_CHECKOUT_ALLOWED_HOSTS = "*.example.test"
        with self.assertRaisesRegex(RuntimeError, "payment_checkout_allowed_hosts_invalid"):
            assert_payment_configuration_safe()

    def test_collection_kill_switch_preserves_history_query_and_refund(self):
        query_order = self._new_order()
        refund_order = self._new_order(amount_cny=Decimal("11.02"))
        refund_amount = self._mark_paid(refund_order)

        settings.PAYMENT_SERVICE_ENABLED = False
        settings.DIRECT_TRADE_ENABLED = False
        settings.QIXIANGPAY_NOTIFY_URL = ""
        settings.QIXIANGPAY_RETURN_URL = ""
        settings.QIXIANGPAY_PAYMENT_TYPES = ""
        assert_payment_configuration_safe()

        with self.assertRaisesRegex(BizError, "尚未完成配置") as stopped:
            create_recharge_order(
                self.db,
                self.user_id,
                Decimal("10.02"),
                payment_type="alipay",
                client_request_id="recharge-kill-switch-0001",
            )
        self.assertEqual(stopped.exception.status_code, 503)

        with patch(
            "app.services.qixiangpay.httpx.get",
            return_value=self._query_response(query_order, status=0),
        ) as provider_query:
            queried = query_provider_and_reconcile(self.db, query_order)
        self.assertEqual(queried["status"], "pending")
        provider_query.assert_called_once()

        with patch(
            "app.services.qixiangpay.httpx.post",
            return_value=FakeResponse({"code": 1, "msg": "退款成功"}),
        ) as provider_refund:
            refunded = request_payment_refund(
                self.db,
                payment_order_id=refund_order.id,
                actor_user_id=self.admin_id,
                client_request_id="refund-kill-switch-0001",
                reason="停收期间处理历史订单退款",
            )
        self.assertEqual(refunded["status"], "succeeded")
        provider_refund.assert_called_once()
        self.db.expire_all()
        wallet = self.db.query(Wallet).filter_by(user_id=self.user_id).one()
        self.assertEqual(wallet.balance, Decimal("0.000000"))
        self.assertEqual(wallet.frozen, Decimal("0.000000"))
        self.assertEqual(refund_amount, Decimal(refund_order.card_hours))

    def test_provider_switch_controls_callback_but_collection_switch_does_not(self):
        accepted_order = self._new_order()
        disabled_order = self._new_order(amount_cny=Decimal("11.02"))
        accepted_callback = self._success_callback(accepted_order)
        disabled_callback = self._success_callback(disabled_order)

        settings.PAYMENT_SERVICE_ENABLED = False
        self.assertTrue(handle_notification(self.db, accepted_callback))
        self.db.expire_all()
        self.assertIsNotNone(self.db.get(PaymentOrder, accepted_order.id).credited_at)

        settings.QIXIANGPAY_ENABLED = False
        with self.assertRaisesRegex(BizError, "历史回调能力") as disabled:
            handle_notification(self.db, disabled_callback)
        self.assertEqual(disabled.exception.status_code, 503)
        self.db.rollback()
        self.db.expire_all()
        current = self.db.get(PaymentOrder, disabled_order.id)
        self.assertEqual(current.status, "pending")
        self.assertIsNone(current.credited_at)

    def test_uncredited_review_refund_stays_refunded_after_callback_redelivery(self):
        order = self._new_order()
        order.status = "review"
        order.provider_status = "TRADE_SUCCESS"
        order.provider_trade_no = f"QX-{order.order_no}"
        self.db.commit()

        with patch(
            "app.services.qixiangpay.submit_provider_refund",
            return_value={"success": True, "code": "1", "msg": "退款成功"},
        ):
            result = request_payment_refund(
                self.db,
                payment_order_id=order.id,
                actor_user_id=self.admin_id,
                client_request_id="refund-review-callback-0001",
                reason="未入账订单原路退款",
            )
        self.assertEqual(result["status"], "succeeded")

        callback = self._success_callback(order)
        self.assertTrue(handle_notification(self.db, callback))
        self.assertTrue(handle_notification(self.db, callback))
        self.db.expire_all()
        current = self.db.get(PaymentOrder, order.id)
        self.assertEqual(current.status, "refunded")
        self.assertIsNone(current.credited_at)
        self.assertEqual(self.db.get(Wallet, self.wallet.id).balance, Decimal("0.000000"))
        self.assertEqual(
            self.db.query(Ledger).filter_by(ref_payment_order_id=order.id).count(),
            0,
        )
        events = self.db.query(PaymentEvent).filter_by(
            payment_order_id=order.id,
            event_type="provider_success_during_refund",
        ).all()
        self.assertEqual(len(events), 1)
        self.assertEqual(events[0].detail["provider_status"], "TRADE_SUCCESS")

    def test_refund_pending_wins_over_stale_concurrent_success_callback(self):
        order = self._new_order()
        order.status = "review"
        order.provider_status = "TRADE_SUCCESS"
        order.provider_trade_no = f"QX-{order.order_no}"
        self.db.commit()
        callback = self._success_callback(order)

        callback_db = self.Session()
        stale_order = callback_db.get(PaymentOrder, order.id)
        self.assertEqual(stale_order.status, "review")

        def callback_during_provider_submission(_order):
            # This session loaded the order before the refund committed its
            # claim.  The atomic status predicate, not the in-memory object,
            # must decide whether credit is still allowed.
            self.assertTrue(handle_notification(callback_db, callback))
            current = self.Session()
            try:
                protected = current.get(PaymentOrder, order.id)
                self.assertEqual(protected.status, "refund_pending")
                self.assertIsNone(protected.credited_at)
            finally:
                current.close()
            raise ProviderRefundUncertain("timeout", status_code=502)

        try:
            with patch(
                "app.services.qixiangpay.submit_provider_refund",
                side_effect=callback_during_provider_submission,
            ):
                result = request_payment_refund(
                    self.db,
                    payment_order_id=order.id,
                    actor_user_id=self.admin_id,
                    client_request_id="refund-concurrent-callback-0001",
                    reason="并发回调竞态测试",
                )
        finally:
            callback_db.close()
        self.assertEqual(result["status"], "unknown")
        self.db.expire_all()
        current = self.db.get(PaymentOrder, order.id)
        self.assertEqual(current.status, "refund_unknown")
        self.assertIsNone(current.credited_at)
        self.assertEqual(self.db.get(Wallet, self.wallet.id).balance, Decimal("0.000000"))
        self.assertEqual(
            self.db.query(Ledger).filter_by(ref_payment_order_id=order.id).count(),
            0,
        )
        self.assertEqual(
            self.db.query(PaymentEvent).filter_by(
                payment_order_id=order.id,
                event_type="provider_success_during_refund",
            ).count(),
            1,
        )

    def test_concurrent_review_credit_forces_refund_retry_with_wallet_hold(self):
        order = self._new_order()
        order.status = "review"
        order.provider_status = "TRADE_SUCCESS"
        order.provider_trade_no = f"QX-{order.order_no}"
        self.db.commit()
        request_id = "refund-credit-race-0001"

        def credit_before_refund_claim(_order):
            credit_db = self.Session()
            try:
                current = credit_db.get(PaymentOrder, order.id)
                payload = json.loads(self._query_response(current, status=1).content)
                payload["trade_status"] = "TRADE_SUCCESS"
                self.assertTrue(credit_verified_payment(
                    credit_db,
                    current,
                    payload,
                    review_override=True,
                    actor_user_id=self.admin_id,
                    review_note="并发复核入账",
                ))
            finally:
                credit_db.close()

        with patch(
            "app.services.qixiangpay.assert_provider_refund_ready",
            side_effect=credit_before_refund_claim,
        ), patch("app.services.qixiangpay.submit_provider_refund") as submit:
            with self.assertRaisesRegex(BizError, "状态已变化") as raced:
                request_payment_refund(
                    self.db,
                    payment_order_id=order.id,
                    actor_user_id=self.admin_id,
                    client_request_id=request_id,
                    reason="复核与退款并发",
                )
        self.assertEqual(raced.exception.status_code, 409)
        submit.assert_not_called()
        self.db.expire_all()
        current = self.db.get(PaymentOrder, order.id)
        self.assertEqual(current.status, "paid")
        self.assertIsNotNone(current.credited_at)
        self.assertEqual(self.db.get(Wallet, self.wallet.id).balance, order.card_hours)
        self.assertEqual(self.db.query(PaymentRefund).count(), 0)

        with patch(
            "app.services.qixiangpay.submit_provider_refund",
            return_value={"success": True, "code": "1", "msg": "退款成功"},
        ):
            retried = request_payment_refund(
                self.db,
                payment_order_id=order.id,
                actor_user_id=self.admin_id,
                client_request_id=request_id,
                reason="刷新后重试退款",
            )
        self.assertEqual(retried["status"], "succeeded")
        self.db.expire_all()
        wallet = self.db.get(Wallet, self.wallet.id)
        self.assertEqual(wallet.balance, Decimal("0.000000"))
        self.assertEqual(wallet.frozen, Decimal("0.000000"))

    def test_fresh_submitting_refund_cannot_be_manually_resolved(self):
        order = self._new_order()
        self._mark_paid(order)

        def resolve_while_provider_is_running(_order):
            admin_db = self.Session()
            try:
                refund = admin_db.query(PaymentRefund).filter_by(
                    payment_order_id=order.id
                ).one()
                self.assertEqual(refund.status, "submitting")
                with self.assertRaisesRegex(BizError, "结果不确定") as active:
                    resolve_unknown_refund(
                        admin_db,
                        refund_id=refund.id,
                        actor_user_id=self.admin_id,
                        outcome="failed",
                        note="上游请求尚未结束，不能人工改判",
                    )
                self.assertEqual(active.exception.status_code, 409)
                admin_db.rollback()
            finally:
                admin_db.close()
            return {"success": True, "code": "1", "msg": "退款成功"}

        with patch(
            "app.services.qixiangpay.submit_provider_refund",
            side_effect=resolve_while_provider_is_running,
        ):
            result = request_payment_refund(
                self.db,
                payment_order_id=order.id,
                actor_user_id=self.admin_id,
                client_request_id="refund-active-resolve-0001",
                reason="活动请求人工改判保护",
            )
        self.assertEqual(result["status"], "succeeded")
        self.db.expire_all()
        self.assertEqual(self.db.get(PaymentOrder, order.id).status, "refunded")
        self.assertEqual(self.db.get(Wallet, self.wallet.id).balance, Decimal("0.000000"))

    def test_stale_recovery_cannot_overwrite_concurrent_manual_terminal_result(self):
        order = self._new_order()
        amount = self._mark_paid(order)
        self.wallet.balance = Decimal("0.000000")
        self.wallet.frozen = amount
        order.status = "refund_pending"
        refund = PaymentRefund(
            refund_no="KAIRRECOVERYRACE0001",
            payment_order_id=order.id,
            actor_user_id=self.admin_id,
            client_request_id="refund-recovery-race-0001",
            amount_cny=order.amount_cny,
            card_hours=order.card_hours,
            status="submitting",
            wallet_hold_status="held",
            previous_payment_status="paid",
            reason="超时恢复与人工确认竞态",
            attempt_count=1,
            requested_at=order.created_at - timedelta(hours=1),
        )
        self.db.add(refund)
        self.db.commit()

        recovery_db = self.Session()
        second_worker_db = self.Session()
        admin_db = self.Session()
        original_all = Query.all
        interleaved = {"done": False}

        def resolve_after_other_worker_recovers(query):
            rows = original_all(query)
            if query.session is recovery_db and not interleaved["done"]:
                interleaved["done"] = True
                # Release the candidate reader before the other SQLite writer;
                # the already fetched id remains the first worker's stale view.
                recovery_db.rollback()
                self.assertEqual(
                    recover_stale_refund_submissions(second_worker_db),
                    1,
                )
                resolved = resolve_unknown_refund(
                    admin_db,
                    refund_id=refund.id,
                    actor_user_id=self.reviewer_id,
                    outcome="succeeded",
                    note="商户后台已确认退款成功",
                )
                self.assertEqual(resolved["status"], "succeeded")
            return rows

        try:
            with patch.object(Query, "all", resolve_after_other_worker_recovers):
                changed = recover_stale_refund_submissions(recovery_db)
        finally:
            recovery_db.close()
            second_worker_db.close()
            admin_db.close()
        self.assertEqual(changed, 0)
        self.db.expire_all()
        current_refund = self.db.get(PaymentRefund, refund.id)
        current_order = self.db.get(PaymentOrder, order.id)
        wallet = self.db.get(Wallet, self.wallet.id)
        self.assertEqual(current_refund.status, "succeeded")
        self.assertEqual(current_refund.wallet_hold_status, "settled")
        self.assertEqual(current_order.status, "refunded")
        self.assertEqual(wallet.balance, Decimal("0.000000"))
        self.assertEqual(wallet.frozen, Decimal("0.000000"))
        self.assertEqual(
            self.db.query(Ledger).filter_by(ref_payment_refund_id=refund.id).count(),
            1,
        )

    def test_bounded_reconciliation_claims_each_order_once_per_window(self):
        order = self._new_order()
        order.provider_trade_no = f"QX-{order.order_no}"
        self.db.commit()
        settings.PAYMENT_RECONCILIATION_ENABLED = True
        run_at = order.created_at.replace(microsecond=0) + timedelta(seconds=60)
        with patch(
            "app.services.payment_reconciliation.query_provider_and_reconcile",
            return_value={"status": "pending"},
        ) as query:
            first = reconcile_payment_orders(self.db, now=run_at)
            second = reconcile_payment_orders(self.db, now=run_at)
        self.assertEqual(first, {"claimed": 1, "reconciled": 1, "errors": 0})
        self.assertEqual(second, {"claimed": 0, "reconciled": 0, "errors": 0})
        query.assert_called_once()
        self.db.expire_all()
        self.assertEqual(self.db.get(PaymentOrder, order.id).reconcile_attempts, 1)

    def test_payment_schema_has_idempotency_index(self):
        indexes = {item["name"] for item in inspect(self.engine).get_indexes("payment_orders")}
        self.assertIn("ux_payment_order_user_provider_request", indexes)

    def test_legacy_ledger_migration_adds_payment_refund_reference(self):
        legacy_engine = create_engine("sqlite://")
        try:
            with legacy_engine.begin() as connection:
                connection.execute(text("CREATE TABLE ledger (id INTEGER PRIMARY KEY)"))
            init_db._ensure_columns(legacy_engine)
            init_db._ensure_columns(legacy_engine)
            columns = {
                item["name"] for item in inspect(legacy_engine).get_columns("ledger")
            }
            self.assertIn("ref_payment_refund_id", columns)
        finally:
            legacy_engine.dispose()


if __name__ == "__main__":
    unittest.main()
