import unittest
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from unittest.mock import patch

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.db.base import Base
from app.models import (
    PaymentEvent,
    PaymentOrder,
    PaymentRefund,
    PaymentRefundRequest,
    User,
    Wallet,
)
from app.services.account_deletion_data import get_deletion_blockers
from app.services.payment_refund_requests import (
    create_refund_request,
    get_refund_request_for_order,
    list_owned_refund_requests,
    assert_no_active_customer_refund_request,
    get_admin_refund_request,
    list_admin_refund_requests,
    review_refund_request,
    sync_refund_request_for_payment_refund,
)
from app.services.payment_operations import request_payment_refund, resolve_unknown_refund
from app.services.qixiangpay import ProviderRefundUncertain
from app.utils.response import BizError


def utc_now() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


class PaymentRefundRequestTests(unittest.TestCase):
    def setUp(self):
        self.engine = create_engine(
            "sqlite://",
            connect_args={"check_same_thread": False},
            poolclass=StaticPool,
        )
        Base.metadata.create_all(self.engine)
        self.Session = sessionmaker(bind=self.engine, expire_on_commit=False)
        self.db = self.Session()
        self.user = User(phone="13900002901", username="退款申请用户", password="!")
        self.other = User(phone="13900002902", username="其他用户", password="!")
        self.admin = User(
            phone="13900002903", username="退款管理员", password="!", role="admin"
        )
        self.admin2 = User(
            phone="13900002904", username="复核管理员", password="!", role="admin"
        )
        self.db.add_all((self.user, self.other, self.admin, self.admin2))
        self.db.flush()
        self.wallet = Wallet(
            user_id=self.user.id,
            balance=Decimal("20.000000"),
            frozen=Decimal("0.000000"),
        )
        self.other_wallet = Wallet(
            user_id=self.other.id,
            balance=Decimal("20.000000"),
            frozen=Decimal("0.000000"),
        )
        self.db.add_all((self.wallet, self.other_wallet))
        self.order = self._paid_order(self.user.id, "KAIR-REFUND-REQUEST-1")
        self.other_order = self._paid_order(self.other.id, "KAIR-REFUND-REQUEST-2")
        self.db.commit()

    def tearDown(self):
        self.db.close()
        self.engine.dispose()

    def _paid_order(
        self,
        user_id: int,
        order_no: str,
        *,
        provider: str = "qixiangpay",
        status: str = "paid",
        credited: bool = True,
    ) -> PaymentOrder:
        row = PaymentOrder(
            order_no=order_no,
            user_id=user_id,
            provider=provider,
            channel="alipay",
            status=status,
            amount_cny=Decimal("10.00"),
            card_hours=Decimal("9.980040"),
            card_hour_rate=Decimal("1.002000"),
            checkout_token_hash=f"token-{order_no}",
            expires_at=utc_now() + timedelta(minutes=5),
            paid_at=utc_now() if credited else None,
            credited_at=utc_now() if credited else None,
        )
        self.db.add(row)
        self.db.flush()
        return row

    def _create(
        self,
        *,
        order_no: str | None = None,
        request_id: str = "refund-application-0001",
        reason: str = "不再需要本次充值服务",
    ) -> dict:
        return create_refund_request(
            self.db,
            user_id=self.user.id,
            order_no=order_no or self.order.order_no,
            client_request_id=request_id,
            reason=reason,
            platform="android",
        )

    def test_submission_records_review_request_without_financial_side_effects(self):
        before_status = self.order.status
        result = self._create(reason="  不再需要本次   充值服务  ")

        self.assertEqual(result["status"], "pending_review")
        self.assertEqual(result["reason"], "不再需要本次 充值服务")
        self.assertEqual(result["created_platform"], "android")
        self.assertEqual(result["amount_cny"], 10.0)
        self.assertEqual(result["card_hours"], 9.98004)
        self.assertEqual(self.db.query(PaymentRefundRequest).count(), 1)
        self.assertEqual(self.db.query(PaymentRefund).count(), 0)
        self.db.refresh(self.order)
        self.assertEqual(self.order.status, before_status)
        event = self.db.query(PaymentEvent).filter_by(
            payment_order_id=self.order.id,
            event_type="customer_refund_requested",
        ).one()
        self.assertEqual(event.actor_type, "user")
        self.assertEqual(event.actor_user_id, self.user.id)

    def test_retries_are_idempotent_for_request_key_and_active_order(self):
        first = self._create()
        same_key = self._create()
        new_key = self._create(request_id="refund-application-0002")

        self.assertEqual(first["id"], same_key["id"])
        self.assertEqual(first["id"], new_key["id"])
        self.assertEqual(self.db.query(PaymentRefundRequest).count(), 1)
        self.assertEqual(
            self.db.query(PaymentEvent).filter_by(
                event_type="customer_refund_requested"
            ).count(),
            1,
        )

    def test_reusing_idempotency_key_for_different_payload_is_rejected(self):
        self._create()
        with self.assertRaises(BizError) as reason_error:
            self._create(reason="另一个完全不同的退款原因")
        self.assertEqual(reason_error.exception.status_code, 409)

        second = self._paid_order(self.user.id, "KAIR-REFUND-REQUEST-3")
        self.db.commit()
        with self.assertRaises(BizError) as order_error:
            self._create(order_no=second.order_no)
        self.assertEqual(order_error.exception.status_code, 409)

    def test_service_rejects_invalid_idempotency_key_and_reason(self):
        with self.assertRaises(BizError) as request_id_error:
            self._create(request_id="too-short")
        self.assertEqual(request_id_error.exception.status_code, 400)
        with self.assertRaises(BizError) as reason_error:
            self._create(reason="  退款  ")
        self.assertEqual(reason_error.exception.status_code, 400)

    def test_only_owned_verified_qixiang_orders_are_eligible(self):
        with self.assertRaises(BizError) as ownership_error:
            self._create(order_no=self.other_order.order_no)
        self.assertEqual(ownership_error.exception.status_code, 404)

        unpaid = self._paid_order(
            self.user.id,
            "KAIR-REFUND-REQUEST-4",
            status="pending",
            credited=False,
        )
        legacy = self._paid_order(
            self.user.id,
            "KAIR-REFUND-REQUEST-5",
            provider="mapay",
        )
        self.db.commit()
        with self.assertRaises(BizError) as unpaid_error:
            self._create(
                order_no=unpaid.order_no,
                request_id="refund-application-unpaid",
            )
        self.assertEqual(unpaid_error.exception.status_code, 409)
        with self.assertRaises(BizError) as legacy_error:
            self._create(
                order_no=legacy.order_no,
                request_id="refund-application-legacy",
            )
        self.assertEqual(legacy_error.exception.status_code, 409)

    def test_existing_provider_refund_blocks_customer_application(self):
        refund = PaymentRefund(
            refund_no="KAIRPROVIDERREFUND0001",
            payment_order_id=self.order.id,
            actor_user_id=self.other.id,
            client_request_id="admin-refund-request-0001",
            amount_cny=self.order.amount_cny,
            card_hours=self.order.card_hours,
            status="unknown",
            wallet_hold_status="held",
            previous_payment_status="paid",
            reason="管理员已处理退款",
        )
        self.db.add(refund)
        self.db.commit()
        with self.assertRaises(BizError) as error:
            self._create()
        self.assertEqual(error.exception.status_code, 409)

    def test_list_get_and_deletion_blocker_are_user_scoped(self):
        created = self._create()
        other_created = create_refund_request(
            self.db,
            user_id=self.other.id,
            order_no=self.other_order.order_no,
            client_request_id="refund-other-user-0001",
            reason="其他用户申请充值退款",
            platform="ios",
        )

        detail = get_refund_request_for_order(
            self.db,
            user_id=self.user.id,
            order_no=self.order.order_no,
        )
        listing = list_owned_refund_requests(
            self.db,
            user_id=self.user.id,
            page=1,
            page_size=20,
            status="pending_review",
        )
        self.assertEqual(detail["id"], created["id"])
        self.assertEqual(listing["total"], 1)
        self.assertEqual(listing["items"][0]["id"], created["id"])
        self.assertNotEqual(created["id"], other_created["id"])
        with self.assertRaises(BizError) as hidden:
            get_refund_request_for_order(
                self.db,
                user_id=self.user.id,
                order_no=self.other_order.order_no,
            )
        self.assertEqual(hidden.exception.status_code, 404)

        blockers = get_deletion_blockers(self.db, self.user)
        blocker_codes = {item["code"] for item in blockers}
        self.assertIn("pending_refund_requests", blocker_codes)

    def test_admin_rejection_is_terminal_and_allows_a_new_application(self):
        created = self._create()
        reviewed = review_refund_request(
            self.db,
            request_id=created["id"],
            actor_user_id=self.admin.id,
            action="reject",
            note="订单不符合原路退款条件",
        )

        self.assertEqual(reviewed["status"], "rejected")
        self.assertEqual(reviewed["reviewed_by"], self.admin.id)
        self.assertEqual(reviewed["review_note"], "订单不符合原路退款条件")
        self.assertIsNone(reviewed["payment_refund"])
        self.assertEqual(self.db.query(PaymentRefund).count(), 0)
        self.db.refresh(self.order)
        self.assertEqual(self.order.status, "paid")

        replacement = self._create(request_id="refund-application-retry")
        self.assertEqual(replacement["status"], "pending_review")
        self.assertNotEqual(replacement["id"], created["id"])

    def test_admin_approval_runs_existing_original_rail_refund_saga(self):
        created = self._create()
        with patch(
            "app.services.qixiangpay.assert_provider_refund_ready"
        ), patch(
            "app.services.qixiangpay.submit_provider_refund",
            return_value={"success": True, "code": "1", "msg": "ok"},
        ) as submit:
            reviewed = review_refund_request(
                self.db,
                request_id=created["id"],
                actor_user_id=self.admin.id,
                action="approve",
                note="核对订单和支付凭证后同意退款",
            )

        submit.assert_called_once()
        self.assertEqual(reviewed["status"], "succeeded")
        self.assertEqual(reviewed["payment_refund"]["status"], "succeeded")
        self.assertIn("用户申请：", reviewed["payment_refund"]["reason"])
        self.assertIn("管理员审核：", reviewed["payment_refund"]["reason"])
        self.db.refresh(self.order)
        self.db.refresh(self.wallet)
        self.assertEqual(self.order.status, "refunded")
        self.assertEqual(self.wallet.frozen, Decimal("0.000000"))
        self.assertEqual(self.wallet.balance, Decimal("10.019960"))

    def test_failed_approval_precondition_leaves_application_pending(self):
        created = self._create()
        self.wallet.balance = Decimal("0.000000")
        self.db.commit()
        with patch("app.services.qixiangpay.assert_provider_refund_ready"):
            with self.assertRaises(BizError) as error:
                review_refund_request(
                    self.db,
                    request_id=created["id"],
                    actor_user_id=self.admin.id,
                    action="approve",
                    note="同意退款但余额不足",
                )
        self.assertEqual(error.exception.status_code, 409)
        current = self.db.get(PaymentRefundRequest, created["id"])
        self.assertEqual(current.status, "pending_review")
        self.assertIsNone(current.reviewed_by)
        self.assertEqual(self.db.query(PaymentRefund).count(), 0)
        self.db.refresh(self.order)
        self.assertEqual(self.order.status, "paid")

    def test_unknown_refund_resolution_updates_customer_application(self):
        created = self._create()
        with patch(
            "app.services.qixiangpay.assert_provider_refund_ready"
        ), patch(
            "app.services.qixiangpay.submit_provider_refund",
            side_effect=ProviderRefundUncertain("unknown", status_code=502),
        ):
            reviewed = review_refund_request(
                self.db,
                request_id=created["id"],
                actor_user_id=self.admin.id,
                action="approve",
                note="同意退款并提交支付渠道",
            )
        self.assertEqual(reviewed["status"], "processing")
        refund_id = reviewed["payment_refund"]["id"]
        self.assertEqual(reviewed["payment_refund"]["status"], "unknown")

        resolve_unknown_refund(
            self.db,
            refund_id=refund_id,
            actor_user_id=self.admin2.id,
            outcome="succeeded",
            note="已依据商户后台退款凭证复核",
        )
        synced = sync_refund_request_for_payment_refund(self.db, refund_id)
        self.assertEqual(synced["status"], "succeeded")
        self.assertEqual(synced["payment_refund"]["status"], "succeeded")

    def test_direct_admin_refund_is_blocked_while_customer_request_is_active(self):
        created = self._create()
        with self.assertRaises(BizError) as error:
            assert_no_active_customer_refund_request(self.db, self.order.id)
        self.assertEqual(error.exception.status_code, 409)
        with patch("app.services.qixiangpay.assert_provider_refund_ready") as ready:
            with self.assertRaises(BizError) as service_error:
                request_payment_refund(
                    self.db,
                    payment_order_id=self.order.id,
                    actor_user_id=self.admin.id,
                    client_request_id="direct-admin-refund-0001",
                    reason="绕过申请队列直接退款",
                )
        self.assertEqual(service_error.exception.status_code, 409)
        ready.assert_not_called()

        review_refund_request(
            self.db,
            request_id=created["id"],
            actor_user_id=self.admin.id,
            action="reject",
            note="暂不符合退款条件",
        )
        self.assertIsNone(
            assert_no_active_customer_refund_request(self.db, self.order.id)
        )

    def test_admin_list_and_detail_include_linked_order_but_not_other_filters(self):
        created = self._create()
        create_refund_request(
            self.db,
            user_id=self.other.id,
            order_no=self.other_order.order_no,
            client_request_id="refund-other-user-admin-list",
            reason="其他用户申请充值退款",
            platform="ios",
        )
        listing = list_admin_refund_requests(
            self.db,
            page=1,
            page_size=20,
            status="pending_review",
            order_no=self.order.order_no,
            platform="android",
        )
        detail = get_admin_refund_request(self.db, created["id"])

        self.assertEqual(listing["total"], 1)
        self.assertEqual(listing["items"][0]["id"], created["id"])
        self.assertEqual(detail["order_no"], self.order.order_no)
        self.assertEqual(detail["user"]["id"], self.user.id)


if __name__ == "__main__":
    unittest.main()
