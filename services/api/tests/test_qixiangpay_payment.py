import hmac
import json
import tempfile
import threading
import unittest
from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta, timezone
from decimal import Decimal
from pathlib import Path
from unittest.mock import patch
from zoneinfo import ZoneInfo

import httpx
from sqlalchemy import create_engine, inspect, text
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.core.config import settings
from app.db.base import Base
from app.models import Ledger, PaymentOrder, User, Wallet  # noqa: F401
from app.routers import qixiang_payment as payment_router
from app.services.qixiangpay import (
    CREATE_PENDING,
    CREATE_UNKNOWN,
    _checkout_redirect_url_locked,
    canonicalize,
    cancel_recharge_order,
    checkout_redirect_url,
    credit_verified_payment,
    create_recharge_order,
    handle_notification,
    public_config,
    query_provider_and_reconcile,
    resolve_checkout_client_ip,
    sign_params,
    utc_now,
    verify_params,
)
from app.utils.response import BizError
import init_db


class FakeResponse:
    def __init__(self, payload: dict | None = None, *, content: bytes | None = None):
        self.content = content if content is not None else json.dumps(payload).encode("utf-8")

    def raise_for_status(self):
        return None


class QixiangPayPaymentTests(unittest.TestCase):
    def setUp(self):
        self.engine = create_engine(
            "sqlite://",
            connect_args={"check_same_thread": False},
            poolclass=StaticPool,
        )
        Base.metadata.create_all(self.engine)
        self.Session = sessionmaker(bind=self.engine, expire_on_commit=False)
        self.db = self.Session()
        self.user = User(phone="13900001901", username="七相支付测试", password="!")
        self.db.add(self.user)
        self.db.flush()
        self.wallet = Wallet(user_id=self.user.id, balance=Decimal("10"), frozen=Decimal("0"))
        self.db.add(self.wallet)
        self.db.commit()

        names = (
            "PAYMENT_SERVICE_ENABLED",
            "SECRET_KEY",
            "QIXIANGPAY_ENABLED",
            "QIXIANGPAY_BASE_URL",
            "QIXIANGPAY_PID",
            "QIXIANGPAY_KEY",
            "QIXIANGPAY_NOTIFY_URL",
            "QIXIANGPAY_RETURN_URL",
            "QIXIANGPAY_PUBLIC_API_BASE_URL",
            "QIXIANGPAY_PAYMENT_TYPES",
            "QIXIANGPAY_HTTP_TIMEOUT",
            "QIXIANGPAY_MAX_RESPONSE_BYTES",
            "QIXIANGPAY_TRUSTED_PROXY_CIDRS",
            "PAYMENT_CHECKOUT_ALLOWED_HOSTS",
            "QIXIANGPAY_CHECKOUT_TTL_SECONDS",
            "QIXIANGPAY_PROVIDER_TIMEZONE",
            "QIXIANGPAY_MIN_AMOUNT_CNY",
            "QIXIANGPAY_MAX_AMOUNT_CNY",
            "CARD_HOUR_RMB_RATE",
            "PAYMENT_MAX_PENDING_ORDERS_PER_USER",
            "PAYMENT_DAILY_RECHARGE_LIMIT_CNY",
        )
        self.original = {name: getattr(settings, name) for name in names}
        settings.PAYMENT_SERVICE_ENABLED = True
        settings.SECRET_KEY = "unit-test-qixiang-checkout-secret"
        settings.QIXIANGPAY_ENABLED = True
        settings.QIXIANGPAY_BASE_URL = "https://api.payqixiang.cn"
        settings.QIXIANGPAY_PID = "test-pid"
        settings.QIXIANGPAY_KEY = "unit-test-key-not-a-real-secret"
        settings.QIXIANGPAY_NOTIFY_URL = "https://wod.kai.com/api/payments/qixiang/notify"
        settings.QIXIANGPAY_RETURN_URL = "https://wod.kai.com/payment/qixiang/return"
        settings.QIXIANGPAY_PUBLIC_API_BASE_URL = "https://wod.kai.com/api"
        settings.QIXIANGPAY_PAYMENT_TYPES = "alipay,wxpay"
        settings.QIXIANGPAY_HTTP_TIMEOUT = 1
        settings.QIXIANGPAY_MAX_RESPONSE_BYTES = 256 * 1024
        settings.QIXIANGPAY_TRUSTED_PROXY_CIDRS = "127.0.0.1/32,::1/128"
        settings.PAYMENT_CHECKOUT_ALLOWED_HOSTS = "cashier.example.test"
        settings.QIXIANGPAY_CHECKOUT_TTL_SECONDS = 300
        settings.QIXIANGPAY_PROVIDER_TIMEZONE = "Asia/Shanghai"
        settings.QIXIANGPAY_MIN_AMOUNT_CNY = 0.01
        settings.QIXIANGPAY_MAX_AMOUNT_CNY = 50000
        settings.CARD_HOUR_RMB_RATE = 1.002
        settings.PAYMENT_MAX_PENDING_ORDERS_PER_USER = 5
        settings.PAYMENT_DAILY_RECHARGE_LIMIT_CNY = 50000

    def tearDown(self):
        for name, value in self.original.items():
            setattr(settings, name, value)
        self.db.close()
        self.engine.dispose()

    def _new_order(self, channel: str = "alipay") -> tuple[PaymentOrder, str]:
        output = create_recharge_order(
            self.db,
            self.user.id,
            Decimal("0.01"),
            payment_type=channel,
        )
        order = self.db.query(PaymentOrder).filter_by(order_no=output["order_no"]).one()
        token = output["checkout_url"].rsplit("/", 1)[-1]
        return order, token

    @staticmethod
    def _create_response(order: PaymentOrder) -> FakeResponse:
        return FakeResponse({
            "code": 1,
            "msg": "ok",
            "trade_no": f"QX-{order.order_no}",
            "payurl": f"https://cashier.example.test/pay/{order.order_no}",
        })

    def _query_response(self, order: PaymentOrder, *, status: int = 0) -> FakeResponse:
        paid_at = (order.expires_at - timedelta(seconds=1)).replace(
            tzinfo=timezone.utc,
        ).astimezone(ZoneInfo(settings.QIXIANGPAY_PROVIDER_TIMEZONE))
        return FakeResponse({
            "code": 1,
            "msg": "ok",
            "trade_no": f"QX-{order.order_no}",
            "out_trade_no": order.order_no,
            "api_trade_no": "",
            "type": order.channel,
            "pid": settings.QIXIANGPAY_PID,
            "addtime": "2026-08-22 10:00:00",
            "endtime": paid_at.strftime("%Y-%m-%d %H:%M:%S") if status == 1 else "",
            "name": "KAI钱包卡时充值",
            "money": f"{order.amount_cny:.2f}",
            "status": status,
            "param": order.order_no,
            "buyer": "",
        })

    def _file_sqlite_sessions(self):
        tempdir = tempfile.TemporaryDirectory()
        self.addCleanup(tempdir.cleanup)
        database = Path(tempdir.name) / "qixiang-create-concurrency.sqlite3"
        engine = create_engine(
            f"sqlite:///{database.as_posix()}",
            connect_args={"check_same_thread": False, "timeout": 30},
        )
        self.addCleanup(engine.dispose)
        Base.metadata.create_all(engine)
        Session = sessionmaker(bind=engine, expire_on_commit=False)
        seed = Session()
        try:
            user = User(phone="13900001902", username="并发充值测试", password="!")
            seed.add(user)
            seed.flush()
            seed.add(Wallet(user_id=user.id, balance=Decimal("0"), frozen=Decimal("0")))
            seed.commit()
            user_id = int(user.id)
        finally:
            seed.close()
        return Session, user_id

    def _run_parallel_recharge_creates(self, Session, user_id, requests):
        barrier = threading.Barrier(len(requests))

        def create_once(request):
            amount, request_id = request
            db = Session()
            try:
                # Match the real FastAPI dependency path: authentication has
                # already issued a SELECT and SQLAlchemy reports autobegin.
                db.query(User).filter(User.id == user_id).one()
                self.assertTrue(db.in_transaction())
                barrier.wait(timeout=10)
                output = create_recharge_order(
                    db,
                    user_id,
                    amount,
                    payment_type="alipay",
                    client_request_id=request_id,
                )
                return "ok", output
            except BizError as exc:
                db.rollback()
                return "error", {"status_code": exc.status_code, "message": exc.msg}
            finally:
                db.close()

        with patch("app.services.qixiangpay.httpx.post") as provider_create:
            with ThreadPoolExecutor(max_workers=len(requests)) as pool:
                results = list(pool.map(create_once, requests))
        provider_create.assert_not_called()
        return results

    def _callback(self, order: PaymentOrder) -> dict:
        params = {
            "pid": settings.QIXIANGPAY_PID,
            "trade_no": f"QX-{order.order_no}",
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

    def test_md5_canonicalization_and_constant_time_verification(self):
        params = {
            "type": "alipay",
            "pid": "test-pid",
            "empty": "",
            "sign": "ignored",
            "sign_type": "MD5",
        }
        self.assertEqual(canonicalize(params), "pid=test-pid&type=alipay")
        params["sign"] = sign_params(params)
        with patch(
            "app.services.qixiangpay.hmac.compare_digest",
            wraps=hmac.compare_digest,
        ) as compare:
            self.assertTrue(verify_params(params))
        compare.assert_called_once()
        missing_type = dict(params)
        missing_type.pop("sign_type")
        self.assertFalse(verify_params(missing_type))
        wrong_type = dict(params, sign_type="RSA")
        self.assertFalse(verify_params(wrong_type))
        lower_md5 = dict(params, sign_type="md5")
        self.assertTrue(verify_params(lower_md5))

    def test_configured_ten_yuan_minimum_is_enforced(self):
        settings.QIXIANGPAY_MIN_AMOUNT_CNY = 10
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

    def test_new_orders_are_qixiangpay_with_five_minute_deadline(self):
        order, _ = self._new_order()
        self.assertEqual(order.provider, "qixiangpay")
        remaining = (order.expires_at - utc_now()).total_seconds()
        self.assertGreater(remaining, 290)
        self.assertLessEqual(remaining, 300)

    def test_concurrent_daily_limit_admission_is_serialized_across_connections(self):
        settings.PAYMENT_MAX_PENDING_ORDERS_PER_USER = 5
        settings.PAYMENT_DAILY_RECHARGE_LIMIT_CNY = 50000
        Session, user_id = self._file_sqlite_sessions()

        results = self._run_parallel_recharge_creates(
            Session,
            user_id,
            (
                (Decimal("40000.00"), "parallel-daily-limit-0001"),
                (Decimal("40000.00"), "parallel-daily-limit-0002"),
            ),
        )

        self.assertEqual(sorted(kind for kind, _ in results), ["error", "ok"])
        error = next(payload for kind, payload in results if kind == "error")
        self.assertEqual(error["status_code"], 429)
        inspection = Session()
        try:
            orders = inspection.query(PaymentOrder).filter_by(user_id=user_id).all()
            self.assertEqual(len(orders), 1)
            self.assertEqual(
                sum((order.amount_cny for order in orders), Decimal("0")),
                Decimal("40000.00"),
            )
        finally:
            inspection.close()

    def test_concurrent_pending_limit_admission_stops_exactly_at_limit(self):
        settings.PAYMENT_MAX_PENDING_ORDERS_PER_USER = 1
        settings.PAYMENT_DAILY_RECHARGE_LIMIT_CNY = 50000
        Session, user_id = self._file_sqlite_sessions()

        results = self._run_parallel_recharge_creates(
            Session,
            user_id,
            (
                (Decimal("10.00"), "parallel-pending-limit-0001"),
                (Decimal("10.00"), "parallel-pending-limit-0002"),
            ),
        )

        self.assertEqual(sorted(kind for kind, _ in results), ["error", "ok"])
        error = next(payload for kind, payload in results if kind == "error")
        self.assertEqual(error["status_code"], 429)
        inspection = Session()
        try:
            orders = inspection.query(PaymentOrder).filter_by(user_id=user_id).all()
            self.assertEqual(len(orders), 1)
            self.assertEqual(orders[0].status, "pending")
        finally:
            inspection.close()

    def test_concurrent_same_idempotency_key_reuses_one_serialized_order(self):
        Session, user_id = self._file_sqlite_sessions()
        request_id = "parallel-same-idempotency-0001"

        results = self._run_parallel_recharge_creates(
            Session,
            user_id,
            (
                (Decimal("10.00"), request_id),
                (Decimal("10.00"), request_id),
            ),
        )

        self.assertEqual([kind for kind, _ in results], ["ok", "ok"])
        self.assertEqual(
            len({payload["order_no"] for _, payload in results}),
            1,
        )
        inspection = Session()
        try:
            self.assertEqual(
                inspection.query(PaymentOrder).filter_by(
                    user_id=user_id,
                    client_request_id=request_id,
                ).count(),
                1,
            )
        finally:
            inspection.close()

    def test_limit_rejection_does_not_rollback_caller_pending_changes(self):
        settings.PAYMENT_MAX_PENDING_ORDERS_PER_USER = 1
        self._new_order()
        self.user.username = "调用方待提交名称"

        with self.assertRaises(BizError) as rejected:
            create_recharge_order(
                self.db,
                self.user.id,
                Decimal("10.00"),
                payment_type="alipay",
                client_request_id="caller-state-limit-0001",
            )

        self.assertEqual(rejected.exception.status_code, 429)
        self.assertEqual(self.user.username, "调用方待提交名称")
        self.db.commit()
        self.db.refresh(self.user)
        self.assertEqual(self.user.username, "调用方待提交名称")

    def test_legacy_payment_table_migration_adds_checkout_state_columns(self):
        legacy_engine = create_engine("sqlite://")
        try:
            with legacy_engine.begin() as connection:
                connection.execute(text(
                    "CREATE TABLE payment_orders (id INTEGER PRIMARY KEY)"
                ))
            init_db._ensure_columns(legacy_engine)
            # Startup migration is intentionally safe to repeat across workers.
            init_db._ensure_columns(legacy_engine)
            columns = {
                column["name"]: str(column["type"]).upper()
                for column in inspect(legacy_engine).get_columns("payment_orders")
            }
            self.assertIn("provider_checkout_url", columns)
            self.assertIn("checkout_started_at", columns)
            self.assertIn("client_request_id", columns)
            self.assertIn("create_request_hash", columns)
            self.assertIn("last_reconciled_at", columns)
            self.assertIn("reconcile_attempts", columns)
            self.assertEqual(columns["provider_checkout_url"], "TEXT")
            self.assertIn("DATETIME", columns["checkout_started_at"])
        finally:
            legacy_engine.dispose()

    def test_server_side_mapi_post_is_signed_and_cached_for_reopen(self):
        order, token = self._new_order("wxpay")
        response = self._create_response(order)
        with patch("app.services.qixiangpay.httpx.post", return_value=response) as post:
            first = checkout_redirect_url(self.db, token, client_ip="203.0.113.5")
            second = checkout_redirect_url(self.db, token, client_ip="203.0.113.5")
        self.assertEqual(first, second)
        self.assertEqual(post.call_count, 1)
        url, = post.call_args.args
        fields = post.call_args.kwargs["data"]
        self.assertEqual(url, "https://api.payqixiang.cn/mapi.php")
        self.assertEqual(fields["device"], "jump")
        self.assertEqual(fields["type"], "wxpay")
        self.assertEqual(fields["out_trade_no"], order.order_no)
        self.assertEqual(fields["sign"], sign_params(fields))
        self.db.refresh(order)
        self.assertEqual(order.provider_checkout_url, first)

    def test_cached_checkout_never_bypasses_paid_or_canceled_state(self):
        order, token = self._new_order()
        with patch(
            "app.services.qixiangpay.httpx.post",
            return_value=self._create_response(order),
        ):
            checkout_redirect_url(self.db, token, client_ip="203.0.113.6")

        order.status = "canceled"
        self.db.commit()
        with self.assertRaises(BizError) as canceled:
            checkout_redirect_url(self.db, token, client_ip="203.0.113.6")
        self.assertEqual(canceled.exception.status_code, 410)

        order.status = "paid"
        order.credited_at = utc_now()
        self.db.commit()
        with self.assertRaises(BizError) as paid:
            checkout_redirect_url(self.db, token, client_ip="203.0.113.6")
        self.assertEqual(paid.exception.status_code, 410)

    def test_concurrent_double_open_posts_mapi_only_once(self):
        order, token = self._new_order()
        barrier = threading.Barrier(2)

        def open_once(_):
            db = self.Session()
            try:
                barrier.wait(timeout=5)
                return checkout_redirect_url(db, token, client_ip="203.0.113.7")
            finally:
                db.close()

        with patch(
            "app.services.qixiangpay.httpx.post",
            return_value=self._create_response(order),
        ) as post:
            with ThreadPoolExecutor(max_workers=2) as pool:
                urls = list(pool.map(open_once, range(2)))
        self.assertEqual(urls[0], urls[1])
        self.assertEqual(post.call_count, 1)

    def test_fresh_create_pending_is_not_queried_by_another_worker(self):
        order, token = self._new_order()
        outbound_started = threading.Event()
        allow_response = threading.Event()

        def delayed_create(*_args, **_kwargs):
            outbound_started.set()
            if not allow_response.wait(timeout=5):
                raise AssertionError("test did not release provider response")
            return self._create_response(order)

        def first_worker():
            db = self.Session()
            try:
                return checkout_redirect_url(db, token, client_ip="203.0.113.70")
            finally:
                db.close()

        with patch("app.services.qixiangpay.httpx.post", side_effect=delayed_create) as post:
            with ThreadPoolExecutor(max_workers=1) as pool:
                future = pool.submit(first_worker)
                self.assertTrue(outbound_started.wait(timeout=5))
                second_db = self.Session()
                try:
                    with patch("app.services.qixiangpay.httpx.get") as query:
                        with self.assertRaises(BizError) as in_flight:
                            # Bypass the per-process lock to model a second
                            # production worker with its own lock instance.
                            _checkout_redirect_url_locked(
                                second_db,
                                token,
                                client_ip="203.0.113.71",
                            )
                    self.assertEqual(in_flight.exception.status_code, 409)
                    self.assertIn("正在创建", in_flight.exception.msg)
                    query.assert_not_called()
                finally:
                    second_db.close()
                    allow_response.set()
                created_url = future.result(timeout=5)
        self.assertTrue(created_url.startswith("https://cashier.example.test/"))
        self.assertEqual(post.call_count, 1)
        self.db.refresh(order)
        self.assertIsNone(order.checkout_started_at)

    def test_upstream_success_but_local_timeout_never_reposts_same_order(self):
        order, token = self._new_order()
        exposed_secret = settings.QIXIANGPAY_KEY
        with patch(
            "app.services.qixiangpay.httpx.post",
            side_effect=httpx.ReadTimeout(f"timeout key={exposed_secret}"),
        ):
            with self.assertRaises(BizError) as timeout_error:
                checkout_redirect_url(self.db, token, client_ip="203.0.113.8")
        self.assertNotIn(exposed_secret, timeout_error.exception.msg)
        self.assertIsNone(timeout_error.exception.__cause__)
        self.db.refresh(order)
        self.assertEqual(order.provider_status, CREATE_UNKNOWN)

        with patch(
            "app.services.qixiangpay.httpx.get",
            return_value=self._query_response(order, status=0),
        ) as query, patch("app.services.qixiangpay.httpx.post") as duplicate_post:
            with self.assertRaises(BizError) as uncertain:
                checkout_redirect_url(self.db, token, client_ip="203.0.113.8")
        self.assertEqual(uncertain.exception.status_code, 409)
        query.assert_called_once()
        duplicate_post.assert_not_called()
        self.db.refresh(order)
        self.assertEqual(order.status, "failed")

    def test_callback_signature_amount_and_credit_are_idempotent(self):
        order, _ = self._new_order()
        callback = self._callback(order)
        self.assertTrue(handle_notification(self.db, callback))
        # Repeated authentic notifications are acknowledged but never credited
        # twice, so the provider stops retrying while the ledger stays unique.
        self.assertTrue(handle_notification(self.db, callback))
        self.db.refresh(order)
        self.db.refresh(self.wallet)
        self.assertEqual(order.status, "paid")
        self.assertEqual(self.wallet.balance, Decimal("10.009980"))
        self.assertEqual(
            self.db.query(Ledger).filter_by(ref_payment_order_id=order.id).count(),
            1,
        )

        other, _ = self._new_order()
        tampered = self._callback(other)
        tampered["money"] = "0.02"
        with self.assertRaisesRegex(BizError, "签名无效"):
            handle_notification(self.db, tampered)
        self.db.refresh(self.wallet)
        self.assertEqual(self.wallet.balance, Decimal("10.009980"))

    def test_validly_signed_callback_fields_must_match_local_order(self):
        mutations = {
            "pid": "different-pid",
            "out_trade_no": "KAIR-DIFFERENT",
            "type": "wxpay",
            "money": "0.02",
            "param": "different-param",
        }
        for field, value in mutations.items():
            with self.subTest(field=field):
                order, _ = self._new_order("alipay")
                params = self._callback(order)
                params[field] = value
                params["sign"] = sign_params(params)
                self.assertTrue(verify_params(params))
                with self.assertRaises(BizError):
                    credit_verified_payment(self.db, order, params)
        self.db.refresh(self.wallet)
        self.assertEqual(self.wallet.balance, Decimal("10.000000"))

    def test_query_paid_late_and_unknown_status_reconciliation(self):
        timely, _ = self._new_order()
        with patch(
            "app.services.qixiangpay.httpx.get",
            return_value=self._query_response(timely, status=1),
        ):
            timely_result = query_provider_and_reconcile(self.db, timely)
        self.assertEqual(timely_result["status"], "paid")

        late, _ = self._new_order()
        late.expires_at = utc_now() - timedelta(minutes=2)
        self.db.commit()
        late_paid_at = (late.expires_at + timedelta(seconds=30)).replace(
            tzinfo=timezone.utc,
        ).astimezone(ZoneInfo(settings.QIXIANGPAY_PROVIDER_TIMEZONE))
        late_payload = json.loads(self._query_response(late, status=1).content)
        late_payload["endtime"] = late_paid_at.strftime("%Y-%m-%d %H:%M:%S")
        with patch(
            "app.services.qixiangpay.httpx.get",
            return_value=FakeResponse(late_payload),
        ):
            late_result = query_provider_and_reconcile(self.db, late)
        self.assertEqual(late_result["status"], "late_paid_review")
        self.assertIsNone(late_result["credited_at"])

        unknown, _ = self._new_order()
        with patch(
            "app.services.qixiangpay.httpx.get",
            return_value=self._query_response(unknown, status=7),
        ):
            with self.assertRaises(BizError) as unknown_error:
                query_provider_and_reconcile(self.db, unknown)
        self.assertEqual(unknown_error.exception.status_code, 502)

    def test_unpaid_query_cannot_overwrite_concurrent_success_callback(self):
        order, _ = self._new_order()
        order.expires_at = utc_now() - timedelta(seconds=2)
        self.db.commit()
        callback = self._callback(order)
        paid_before_deadline = (order.expires_at - timedelta(seconds=1)).replace(
            tzinfo=timezone.utc,
        ).astimezone(ZoneInfo(settings.QIXIANGPAY_PROVIDER_TIMEZONE))
        callback["endtime"] = paid_before_deadline.strftime("%Y-%m-%d %H:%M:%S")
        callback["sign"] = sign_params(callback)
        unpaid = self._query_response(order, status=0)

        def callback_then_unpaid(*_args, **_kwargs):
            callback_db = self.Session()
            try:
                self.assertTrue(handle_notification(callback_db, callback))
            finally:
                callback_db.close()
            return unpaid

        with patch(
            "app.services.qixiangpay.httpx.get",
            side_effect=callback_then_unpaid,
        ):
            result = query_provider_and_reconcile(self.db, order)
        self.assertEqual(result["status"], "paid")
        self.assertEqual(result["provider_status"], "TRADE_SUCCESS")
        self.assertIsNotNone(result["credited_at"])

    def test_cancel_unpaid_response_cannot_overwrite_concurrent_success(self):
        order, _ = self._new_order()
        callback = self._callback(order)
        unpaid = self._query_response(order, status=0)

        def callback_then_unpaid(*_args, **_kwargs):
            callback_db = self.Session()
            try:
                self.assertTrue(handle_notification(callback_db, callback))
            finally:
                callback_db.close()
            return unpaid

        with patch(
            "app.services.qixiangpay.httpx.get",
            side_effect=callback_then_unpaid,
        ):
            with self.assertRaises(BizError) as cancel_error:
                cancel_recharge_order(self.db, order)
        self.assertEqual(cancel_error.exception.status_code, 409)
        current = self.db.query(PaymentOrder).filter_by(id=order.id).populate_existing().one()
        self.assertEqual(current.status, "paid")
        self.assertEqual(current.provider_status, "TRADE_SUCCESS")
        self.assertIsNotNone(current.credited_at)

    def test_stale_failure_notification_cannot_overwrite_concurrent_success(self):
        order, _ = self._new_order()
        order.expires_at = utc_now() - timedelta(seconds=2)
        self.db.commit()

        stale_db = self.Session()
        stale_db.query(PaymentOrder).filter_by(id=order.id).one()
        success = self._callback(order)
        paid_before_deadline = (order.expires_at - timedelta(seconds=1)).replace(
            tzinfo=timezone.utc,
        ).astimezone(ZoneInfo(settings.QIXIANGPAY_PROVIDER_TIMEZONE))
        success["endtime"] = paid_before_deadline.strftime("%Y-%m-%d %H:%M:%S")
        success["sign"] = sign_params(success)

        success_db = self.Session()
        try:
            self.assertTrue(handle_notification(success_db, success))
        finally:
            success_db.close()

        failure = dict(success)
        failure["trade_status"] = "WAIT_BUYER_PAY"
        failure["sign"] = sign_params(failure)
        try:
            self.assertFalse(handle_notification(stale_db, failure))
        finally:
            stale_db.close()

        current = self.db.query(PaymentOrder).filter_by(id=order.id).populate_existing().one()
        self.assertEqual(current.status, "paid")
        self.assertEqual(current.provider_status, "TRADE_SUCCESS")
        self.assertIsNotNone(current.credited_at)

    def test_cancel_rules_and_success_after_cancel_goes_to_review(self):
        expired, _ = self._new_order()
        expired.expires_at = utc_now() - timedelta(seconds=5)
        self.db.commit()
        with patch(
            "app.services.qixiangpay.httpx.get",
            return_value=self._query_response(expired, status=0),
        ):
            canceled = cancel_recharge_order(self.db, expired)
        self.assertEqual(canceled["status"], "canceled")

        canceled_success = self._callback(expired)
        paid_before_deadline = (expired.expires_at - timedelta(seconds=1)).replace(
            tzinfo=timezone.utc,
        ).astimezone(ZoneInfo(settings.QIXIANGPAY_PROVIDER_TIMEZONE))
        canceled_success["endtime"] = paid_before_deadline.strftime("%Y-%m-%d %H:%M:%S")
        canceled_success["sign"] = sign_params(canceled_success)
        self.assertTrue(handle_notification(self.db, canceled_success))
        self.db.refresh(expired)
        self.assertEqual(expired.status, "review")
        self.assertIsNone(expired.credited_at)
        self.assertEqual(
            self.db.query(Ledger).filter_by(ref_payment_order_id=expired.id).count(),
            0,
        )

        active, _ = self._new_order()
        with patch(
            "app.services.qixiangpay.httpx.get",
            return_value=self._query_response(active, status=0),
        ):
            with self.assertRaises(BizError) as active_error:
                cancel_recharge_order(self.db, active)
        self.assertEqual(active_error.exception.status_code, 409)

        paid, _ = self._new_order()
        self.assertTrue(handle_notification(self.db, self._callback(paid)))
        self.db.refresh(paid)
        with patch("app.services.qixiangpay.httpx.get") as unnecessary_query:
            with self.assertRaises(BizError) as paid_error:
                cancel_recharge_order(self.db, paid)
        self.assertEqual(paid_error.exception.status_code, 409)
        unnecessary_query.assert_not_called()

    def test_create_rejects_missing_insecure_or_unapproved_payurl(self):
        for payurl in (
            None,
            "http://cashier.example.test/pay/unsafe",
            "https://evil.example.test/pay/lookalike",
            "https://cashier.example.test:444/pay/wrong-port",
        ):
            with self.subTest(payurl=payurl):
                order, token = self._new_order()
                payload = {
                    "code": 1,
                    "msg": "ok",
                    "trade_no": f"QX-{order.order_no}",
                }
                if payurl is not None:
                    payload["payurl"] = payurl
                with patch(
                    "app.services.qixiangpay.httpx.post",
                    return_value=FakeResponse(payload),
                ):
                    with self.assertRaises(BizError) as invalid_url:
                        checkout_redirect_url(self.db, token, client_ip="203.0.113.72")
                self.assertEqual(invalid_url.exception.status_code, 502)
                self.db.refresh(order)
                self.assertIsNone(order.provider_checkout_url)

    def test_query_requires_trade_number_even_for_unpaid_and_checks_conflict(self):
        missing, _ = self._new_order()
        missing_payload = json.loads(self._query_response(missing, status=0).content)
        missing_payload.pop("trade_no")
        with patch(
            "app.services.qixiangpay.httpx.get",
            return_value=FakeResponse(missing_payload),
        ):
            with self.assertRaises(BizError) as missing_error:
                query_provider_and_reconcile(self.db, missing)
        self.assertEqual(missing_error.exception.status_code, 502)

        conflict, _ = self._new_order()
        conflict.provider_trade_no = "QX-ORIGINAL"
        self.db.commit()
        with patch(
            "app.services.qixiangpay.httpx.get",
            return_value=self._query_response(conflict, status=0),
        ):
            with self.assertRaisesRegex(BizError, "平台订单号发生冲突"):
                query_provider_and_reconcile(self.db, conflict)

    def test_public_config_never_exposes_merchant_key(self):
        config = public_config()
        self.assertNotIn("key", config)
        self.assertNotIn(settings.QIXIANGPAY_KEY, json.dumps(config, ensure_ascii=False))
        self.assertTrue(config["key_configured"])

    def test_checkout_client_ip_headers_require_a_trusted_proxy(self):
        self.assertEqual(
            resolve_checkout_client_ip(
                "127.0.0.1",
                x_real_ip="203.0.113.80",
                x_forwarded_for="198.51.100.1",
            ),
            "203.0.113.80",
        )
        self.assertEqual(
            resolve_checkout_client_ip(
                "127.0.0.1",
                x_forwarded_for="203.0.113.81, 127.0.0.1",
            ),
            "203.0.113.81",
        )
        self.assertEqual(
            resolve_checkout_client_ip(
                "127.0.0.1",
                x_real_ip="not-an-ip",
                x_forwarded_for="203.0.113.82",
            ),
            "127.0.0.1",
        )
        self.assertEqual(
            resolve_checkout_client_ip(
                "198.51.100.83",
                x_real_ip="203.0.113.83",
                x_forwarded_for="203.0.113.84",
            ),
            "198.51.100.83",
        )

    def test_local_only_and_rejected_orders_cancel_without_network(self):
        untouched, _ = self._new_order()
        untouched.expires_at = utc_now() - timedelta(seconds=1)
        self.db.commit()
        with patch("app.services.qixiangpay.httpx.get") as upstream:
            result = cancel_recharge_order(self.db, untouched)
        self.assertEqual(result["status"], "canceled")
        upstream.assert_not_called()

        rejected, _ = self._new_order()
        rejected.status = "failed"
        rejected.provider_status = "CREATE_FAILED"
        rejected.checkout_started_at = None
        self.db.commit()
        with patch("app.services.qixiangpay.httpx.get") as upstream:
            result = cancel_recharge_order(self.db, rejected)
        self.assertEqual(result["status"], "canceled")
        upstream.assert_not_called()

        uncertain, _ = self._new_order()
        uncertain.expires_at = utc_now() - timedelta(seconds=1)
        uncertain.provider_status = CREATE_PENDING
        uncertain.checkout_started_at = utc_now() - timedelta(minutes=1)
        self.db.commit()
        with patch(
            "app.services.qixiangpay.httpx.get",
            return_value=self._query_response(uncertain, status=0),
        ) as upstream:
            result = cancel_recharge_order(self.db, uncertain)
        self.assertEqual(result["status"], "canceled")
        upstream.assert_called_once()

    def test_oversized_mapi_and_query_responses_are_rejected(self):
        settings.QIXIANGPAY_MAX_RESPONSE_BYTES = 1024
        order, token = self._new_order()
        oversized = FakeResponse(content=b"x" * 1025)
        with patch("app.services.qixiangpay.httpx.post", return_value=oversized):
            with self.assertRaises(BizError) as create_error:
                checkout_redirect_url(self.db, token, client_ip="203.0.113.9")
        self.assertEqual(create_error.exception.status_code, 502)
        self.db.refresh(order)
        self.assertEqual(order.provider_status, CREATE_UNKNOWN)

        second, _ = self._new_order()
        with patch("app.services.qixiangpay.httpx.get", return_value=oversized):
            with self.assertRaises(BizError) as query_error:
                query_provider_and_reconcile(self.db, second)
        self.assertEqual(query_error.exception.status_code, 502)

    def test_old_mapay_order_never_uses_qixiang_query_and_router_dispatches_legacy(self):
        old = PaymentOrder(
            order_no="KAIR-LEGACY-MAPAY-1",
            user_id=self.user.id,
            provider="mapay",
            channel="alipay",
            status="expired",
            amount_cny=Decimal("0.01"),
            card_hours=Decimal("0.009980"),
            card_hour_rate=Decimal("1.002000"),
            checkout_token_hash="legacy-mapay-token-hash",
            expires_at=utc_now() - timedelta(seconds=1),
        )
        self.db.add(old)
        self.db.commit()
        with patch("app.services.qixiangpay.httpx.get") as qixiang_query:
            with self.assertRaisesRegex(BizError, "历史充值订单"):
                query_provider_and_reconcile(self.db, old)
        qixiang_query.assert_not_called()

        with patch.object(
            payment_router.legacy_mapay,
            "query_provider_and_reconcile",
            return_value={"provider": "mapay", "status": "expired"},
        ) as legacy_query:
            response = payment_router.query_payment(old.order_no, self.user, self.db)
        self.assertEqual(response["data"]["provider"], "mapay")
        legacy_query.assert_called_once_with(self.db, old)

        history = payment_router.list_payments(
            page=1,
            page_size=20,
            status=None,
            order_no=old.order_no,
            user=self.user,
            db=self.db,
        )["data"]
        self.assertEqual(history["total"], 1)
        self.assertTrue(history["items"][0]["can_query"])
        # The historical MaPay service has no provider-safe close/cancel API in
        # this KAI snapshot, so the shared history must not advertise it.
        self.assertFalse(history["items"][0]["can_cancel"])

    def test_canonical_and_legacy_callback_routes_are_both_registered(self):
        def registered(router):
            result = {}
            for route in router.routes:
                result.setdefault(route.path, set()).update(route.methods)
            return result

        canonical = registered(payment_router.router)
        legacy = registered(payment_router.legacy_router)
        self.assertEqual(canonical["/api/payments/qixiang/notify"], {"GET", "POST"})
        self.assertEqual(legacy["/api/payments/qixiangpay/notify"], {"GET", "POST"})
        route_suffixes = {
            "/config",
            "/recharge-orders",
            "/orders",
            "/orders/{order_no}",
            "/orders/{order_no}/query",
            "/orders/{order_no}/cancel",
            "/checkout/{token}",
            "/notify",
        }
        self.assertEqual(
            {path.removeprefix("/api/payments/qixiang") for path in canonical},
            route_suffixes,
        )

        from app.main import app

        openapi_paths = app.openapi()["paths"]
        self.assertIn("/api/payments/qixiang/notify", openapi_paths)
        self.assertNotIn("/api/payments/qixiangpay/notify", openapi_paths)
        self.assertEqual(
            {path.removeprefix("/api/payments/qixiangpay") for path in legacy},
            route_suffixes,
        )


if __name__ == "__main__":
    unittest.main()
