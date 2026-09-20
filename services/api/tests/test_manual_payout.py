import io
import tempfile
import threading
import unittest
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from pathlib import Path

from cryptography.fernet import Fernet
from PIL import Image
from fastapi import HTTPException, Response
from pydantic import TypeAdapter, ValidationError
from sqlalchemy import create_engine, inspect, text
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.core.config import settings
from app.core.deps import require_admin
from app.core.sensitive import reveal
from app.db.base import Base
from app.models import (
    BankCard,
    FinanceAuditLog,
    Ledger,
    PaymentInstructionGrant,
    PayoutReceipt,
    User,
    Verification,
    Wallet,
    WithdrawalOrder,
)
from app.models.bank_card import BANK_CARD_SENSITIVE_CONSENT_VERSION
from app.routers import bank_card as bank_card_router
from app.routers import finance as finance_router
from app.routers import supplier as supplier_router
from app.routers import wallet as wallet_router
from app.schemas.bank_card import BankCardIn
from app.schemas.withdrawal import FinanceReviewIn, PayoutPaidAt
from app.services.manual_payout import (
    approve_withdrawal,
    cancel_withdrawal,
    create_withdrawal,
    fail_withdrawal,
    mark_paid,
    normalize_paid_at,
    order_out,
    persist_receipt,
    reject_withdrawal,
    utc_now,
    validate_receipt,
    withdrawal_config,
)
from app.services.wallet_balance import spendable_wallet_balance
from app.utils.bank_util import AMBIGUOUS_BANK_BINS, BANK_BINS, detect_bank
from app.utils.response import BizError
from init_db import _ensure_columns, _migrate_manual_payout_fields, _migrate_sensitive_fields


VALID_CARD = "4539578763621486"


def png_bytes() -> bytes:
    stream = io.BytesIO()
    Image.new("RGB", (12, 12), color=(20, 175, 196)).save(stream, format="PNG")
    return stream.getvalue()


class ManualPayoutTests(unittest.TestCase):
    def setUp(self):
        self.engine = create_engine(
            "sqlite://",
            connect_args={"check_same_thread": False},
            poolclass=StaticPool,
        )
        Base.metadata.create_all(self.engine)
        self.Session = sessionmaker(bind=self.engine, expire_on_commit=False)
        self.db = self.Session()
        self.user = User(phone="13900001001", username="提现用户", password="!")
        self.admin = User(
            phone="13900001002",
            username="平台管理员",
            password="!",
            role="admin",
        )
        self.payer = User(
            phone="13900001999",
            username="财务打款员",
            password="!",
            role="admin",
        )
        self.other_payer = User(
            phone="13900001998",
            username="另一财务打款员",
            password="!",
            role="admin",
        )
        self.db.add_all([self.user, self.admin, self.payer, self.other_payer])
        self.db.flush()
        self.wallet = Wallet(
            user_id=self.user.id,
            balance=Decimal("10"),
            frozen=Decimal("0"),
            withdrawable_balance=Decimal("5"),
            withdraw_frozen=Decimal("0"),
        )
        self.verification = Verification(
            user_id=self.user.id,
            real_name="张三",
            id_card="11010519491231002X",
            status="verified",
            front_photo="front.png",
            back_photo="back.png",
            consent_at=datetime(2026, 8, 20, 8, 0, 0),
        )
        self.card = BankCard(
            user_id=self.user.id,
            bank_name="测试银行",
            card_number=VALID_CARD,
            holder="张三",
            phone="13900001001",
            status="active",
            verification_mode="manual_review",
            is_default=True,
            consent_at=datetime(2026, 8, 20, 8, 0, 0),
            consent_version=BANK_CARD_SENSITIVE_CONSENT_VERSION,
        )
        self.db.add_all([self.wallet, self.verification, self.card])
        self.db.commit()

        self.tempdir = tempfile.TemporaryDirectory()
        self.original = {
            name: getattr(settings, name)
            for name in (
                "DIRECT_TRADE_ENABLED", "MANUAL_BANK_CARD_ENABLED", "MANUAL_PAYOUT_ENABLED",
                "PAYOUT_CARD_HOUR_RMB_RATE",
                "PAYOUT_FEE_RATE", "PAYOUT_MIN_CARD_HOURS",
                "PAYOUT_MAX_CARD_HOURS", "PAYOUT_RECEIPT_MAX_BYTES", "UPLOAD_ROOT",
                "REVENUE_SETTLEMENT_ENABLED", "REWARD_SERVICE_ENABLED",
                "SECRET_KEY", "SENSITIVE_DATA_KEY",
            )
        }
        settings.SECRET_KEY = "unit-test-manual-payout-secret"
        settings.SENSITIVE_DATA_KEY = Fernet.generate_key().decode("ascii")
        settings.DIRECT_TRADE_ENABLED = True
        settings.MANUAL_BANK_CARD_ENABLED = True
        settings.MANUAL_PAYOUT_ENABLED = True
        settings.PAYOUT_CARD_HOUR_RMB_RATE = 1.002
        settings.PAYOUT_FEE_RATE = 0
        settings.PAYOUT_MIN_CARD_HOURS = 1
        settings.PAYOUT_MAX_CARD_HOURS = 100000
        settings.PAYOUT_RECEIPT_MAX_BYTES = 5 * 1024 * 1024
        settings.UPLOAD_ROOT = self.tempdir.name
        settings.REVENUE_SETTLEMENT_ENABLED = True
        settings.REWARD_SERVICE_ENABLED = True

    def tearDown(self):
        for name, value in self.original.items():
            setattr(settings, name, value)
        self.db.close()
        self.tempdir.cleanup()

    def _create(self, amount="2", request_id="withdraw-test-0001"):
        return create_withdrawal(
            self.db,
            self.user,
            amount_card_hours=Decimal(amount),
            bank_card_id=self.card.id,
            client_request_id=request_id,
        )

    def _reveal(self, order, actor=None):
        return finance_router.payment_instructions(
            order.id, Response(), True, actor or self.payer, self.db,
        )["data"]

    def test_paid_at_requires_timezone_and_withdrawal_timestamps_are_utc_explicit(self):
        paid_at = TypeAdapter(PayoutPaidAt).validate_python("2026-09-16T16:30:00+08:00")
        self.assertEqual(normalize_paid_at(paid_at), datetime(2026, 9, 16, 8, 30, 0))
        with self.assertRaises(ValidationError):
            TypeAdapter(PayoutPaidAt).validate_python("2026-09-16T16:30:00")
        with self.assertRaisesRegex(BizError, "时区偏移或 Z"):
            normalize_paid_at(datetime(2026, 9, 16, 8, 30, 0))

        order = self._create()
        order.created_at = datetime(2026, 9, 16, 8, 0, 0)
        order.updated_at = datetime(2026, 9, 16, 8, 15, 0)
        order.paid_at = datetime(2026, 9, 16, 16, 30, 0, tzinfo=timezone(timedelta(hours=8)))
        output = order_out(self.db, order)

        self.assertEqual(output["created_at"], "2026-09-16T08:00:00Z")
        self.assertEqual(output["updated_at"], "2026-09-16T08:15:00Z")
        self.assertEqual(output["paid_at"], "2026-09-16T08:30:00Z")

    def test_spendable_excludes_withdrawable_bucket(self):
        self.assertEqual(spendable_wallet_balance(self.wallet, self.db), Decimal("5"))
        # Existing order code can spend at most B-W. Spending five preserves
        # B >= W; a sixth card-hour must be rejected by its existing check.
        self.assertLess(spendable_wallet_balance(self.wallet, self.db), Decimal("6"))
        self.wallet.balance -= Decimal("5")
        self.assertEqual(self.wallet.balance, self.wallet.withdrawable_balance)
        self.assertEqual(spendable_wallet_balance(self.wallet, self.db), Decimal("0"))

    def test_reward_card_hours_are_spendable_but_never_raise_withdrawable_limit(self):
        self.wallet.balance = Decimal("15")
        self.wallet.withdrawable_balance = Decimal("5")
        self.db.add(Ledger(
            user_id=self.user.id,
            wallet_id=self.wallet.id,
            type="invite_first_order_reward",
            direction="in",
            amount=Decimal("10"),
            balance_after=Decimal("10"),
            event_key="test:nonwithdrawable-invite-reward",
            remark="邀请奖励，仅限站内消费",
        ))
        self.db.commit()

        self.assertEqual(spendable_wallet_balance(self.wallet, self.db), Decimal("10"))
        with self.assertRaisesRegex(BizError, "可提现余额不足"):
            self._create(amount="6", request_id="withdraw-reward-forbidden")
        self.db.refresh(self.wallet)
        self.assertEqual(self.wallet.balance, Decimal("15"))
        self.assertEqual(self.wallet.withdrawable_balance, Decimal("5"))

        allowed = self._create(amount="5", request_id="withdraw-earned-only")
        self.assertEqual(allowed.amount_card_hours, Decimal("5.000000"))
        self.db.refresh(self.wallet)
        self.assertEqual(self.wallet.balance, Decimal("10.000000"))
        self.assertEqual(self.wallet.withdrawable_balance, Decimal("0.000000"))

    def test_configured_ten_card_hour_minimum_is_enforced(self):
        settings.PAYOUT_MIN_CARD_HOURS = 10
        self.assertEqual(withdrawal_config()["min_card_hours"], 10.0)
        with self.assertRaises(BizError):
            self._create(amount="9.99", request_id="withdraw-below-minimum")
        self.wallet.balance = Decimal("20")
        self.wallet.withdrawable_balance = Decimal("20")
        self.db.commit()
        output = self._create(amount="10", request_id="withdraw-at-minimum")
        self.assertEqual(output.amount_card_hours, Decimal("10.000000"))

    def test_card_input_rejects_non_digits_and_normalizes_spaces(self):
        with self.assertRaises(ValidationError):
            BankCardIn(
                card_number="4539-5787-6362-1486",
                holder="张三",
                sensitive_consent=True,
            )
        payload = BankCardIn(
            card_number="4539 5787 6362 1486",
            holder="张三",
            sensitive_consent=True,
        )
        self.assertEqual(payload.card_number, VALID_CARD)

    def test_binding_is_registered_format_only_and_phone_is_encrypted(self):
        second_user = User(phone="13900001003", username="绑卡用户", password="!")
        self.db.add(second_user)
        self.db.flush()
        self.db.add(Verification(
            user_id=second_user.id,
            real_name="李四",
            id_card="11010519491231002X",
            status="pending",
        ))
        self.db.commit()
        result = bank_card_router.add_card(
            BankCardIn(
                bank_name="测试银行",
                card_number=VALID_CARD,
                holder="李四",
                phone="13900001003",
                is_default=True,
                sensitive_consent=True,
            ),
            second_user,
            self.db,
        )["data"]
        row = self.db.query(BankCard).filter(BankCard.id == result["id"]).one()
        self.assertEqual(row.status, "registered")
        self.assertEqual(row.verification_mode, "format_only")
        self.assertTrue(row.is_default)
        self.assertFalse(result["bank_verified"])
        self.assertTrue(row.phone.startswith("enc:v1:"))
        self.assertEqual(reveal(row.phone), "13900001003")
        self.assertNotIn("13900001003", str(result))

    def test_admin_manages_finance_but_cannot_self_review(self):
        self.assertIs(require_admin(self.admin), self.admin)
        with self.assertRaises(HTTPException) as unauthorized:
            require_admin(self.user)
        self.assertEqual(unauthorized.exception.status_code, 403)
        access = finance_router.finance_me(self.admin)["data"]
        self.assertTrue(access["is_admin"])
        self.assertTrue(access["is_finance_admin"])
        self.assertFalse(finance_router.finance_me(self.user)["data"]["is_admin"])
        own_verification = Verification(
            user_id=self.admin.id,
            real_name="王五",
            id_card="11010519491231002X",
            status="pending",
            front_photo="front.png",
            back_photo="back.png",
        )
        self.db.add(own_verification)
        self.db.commit()
        with self.assertRaisesRegex(BizError, "不能审核"):
            finance_router.verification_review(
                own_verification.id,
                FinanceReviewIn(approved=True),
                self.admin,
                self.db,
            )

    def test_legacy_card_review_downgrades_to_registered_not_bank_verified(self):
        review_user = User(phone="13900001004", username="审核链路用户", password="!")
        self.db.add(review_user)
        self.db.flush()
        verification = Verification(
            user_id=review_user.id,
            real_name="赵六",
            id_card="11010519491231002X",
            status="pending",
            consent_at=datetime(2026, 8, 20, 8, 0, 0),
        )
        card = BankCard(
            user_id=review_user.id,
            bank_name="测试银行",
            card_number=VALID_CARD,
            holder="赵六",
            status="pending_review",
            verification_mode="manual_review",
        )
        self.db.add_all([verification, card])
        self.db.commit()
        with self.assertRaisesRegex(BizError, "正反面"):
            finance_router.verification_review(
                verification.id, FinanceReviewIn(approved=True), self.admin, self.db,
            )
        verification.front_photo = "front.png"
        verification.back_photo = "back.png"
        self.db.commit()
        finance_router.verification_review(
            verification.id, FinanceReviewIn(approved=True), self.admin, self.db,
        )
        self.db.refresh(verification)
        self.assertEqual(verification.status, "verified")
        output = finance_router.bank_card_review(
            card.id, FinanceReviewIn(approved=True), self.admin, self.db,
        )["data"]
        self.db.refresh(card)
        self.assertEqual(card.status, "registered")
        self.assertEqual(card.verification_mode, "format_only")
        self.assertFalse(output["bank_verified"])
        actions = {row.action for row in self.db.query(FinanceAuditLog).all()}
        self.assertIn("verification.approve", actions)
        self.assertIn("bank_card.approve", actions)

    def test_finance_cannot_approve_identity_without_consent_record(self):
        legacy_user = User(phone="13900001014", username="旧实名用户", password="!")
        self.db.add(legacy_user)
        self.db.flush()
        verification = Verification(
            user_id=legacy_user.id,
            real_name="钱七",
            id_card="11010519491231002X",
            status="pending",
            front_photo="front.png",
            back_photo="back.png",
            consent_at=None,
        )
        self.db.add(verification)
        self.db.commit()
        with self.assertRaisesRegex(BizError, "单独同意") as raised:
            finance_router.verification_review(
                verification.id,
                FinanceReviewIn(approved=True),
                self.admin,
                self.db,
            )
        self.assertEqual(raised.exception.status_code, 409)
        self.db.refresh(verification)
        self.assertEqual(verification.status, "pending")

    def test_registered_card_still_requires_verified_identity_to_withdraw(self):
        self.card.status = "registered"
        self.card.verification_mode = "format_only"
        self.verification.status = "pending"
        self.db.commit()
        with self.assertRaisesRegex(BizError, "实名认证人工审核通过"):
            self._create()

    def test_historical_card_without_current_consent_cannot_withdraw(self):
        self.card.consent_at = None
        self.card.consent_version = None
        self.db.commit()
        with self.assertRaisesRegex(BizError, "缺少当前敏感信息使用同意") as raised:
            self._create(request_id="withdraw-consent-required")
        self.assertEqual(raised.exception.status_code, 409)
        self.db.refresh(self.wallet)
        self.assertEqual(self.wallet.balance, Decimal("10"))
        self.assertEqual(self.wallet.frozen, Decimal("0"))

    def test_ambiguous_bins_are_never_claimed_as_a_bank(self):
        self.assertTrue(AMBIGUOUS_BANK_BINS.isdisjoint(BANK_BINS))
        for prefix in AMBIGUOUS_BANK_BINS:
            self.assertIsNone(detect_bank(prefix + "0000000000"))

    def test_full_card_requires_explicit_reveal_and_payment_pending_status(self):
        order = self._create()
        with self.assertRaisesRegex(BizError, "显式"):
            finance_router.payment_instructions(order.id, Response(), False, self.admin, self.db)
        with self.assertRaisesRegex(BizError, "待人工打款"):
            finance_router.payment_instructions(order.id, Response(), True, self.admin, self.db)
        approve_withdrawal(self.db, order, self.admin, None)
        self.db.refresh(order)
        with self.assertRaisesRegex(BizError, "不同管理员"):
            finance_router.payment_instructions(order.id, Response(), True, self.admin, self.db)
        response = Response()
        output = finance_router.payment_instructions(
            order.id, response, True, self.payer, self.db,
        )["data"]
        self.assertEqual(output["card_number"], VALID_CARD)
        self.assertFalse(output["bank_verified"])
        self.assertTrue(output["reveal_token"])
        self.assertIsNotNone(output["reveal_expires_at"])
        self.assertEqual(response.headers["cache-control"], "private, no-store")
        self.db.refresh(order)
        self.assertEqual(order.payout_actor_id, self.payer.id)
        with self.assertRaisesRegex(BizError, "其他财务经办人"):
            finance_router.payment_instructions(
                order.id, Response(), True, self.other_payer, self.db,
            )
        audit_text = " ".join(row.detail or "" for row in self.db.query(FinanceAuditLog).all())
        self.assertNotIn(VALID_CARD, audit_text)

    def test_freeze_is_atomic_and_client_request_is_idempotent(self):
        order = self._create()
        self.db.refresh(self.wallet)
        self.assertEqual(self.wallet.balance, Decimal("8"))
        self.assertEqual(self.wallet.withdrawable_balance, Decimal("3"))
        self.assertEqual(self.wallet.frozen, Decimal("2"))
        self.assertEqual(self.wallet.withdraw_frozen, Decimal("2"))
        same = self._create()
        self.assertEqual(same.id, order.id)
        self.db.refresh(self.wallet)
        self.assertEqual(self.wallet.balance, Decimal("8"))
        self.assertEqual(self.db.query(Ledger).filter(Ledger.type == "withdraw_freeze").count(), 1)
        with self.assertRaisesRegex(BizError, "请求编号"):
            self._create(amount="1", request_id="withdraw-test-0001")

    def test_second_request_cannot_overdraw_withdrawable_balance(self):
        self._create(amount="4", request_id="withdraw-atomic-0001")
        with self.assertRaisesRegex(BizError, "可提现余额不足"):
            self._create(amount="2", request_id="withdraw-atomic-0002")
        self.db.refresh(self.wallet)
        self.assertEqual(self.wallet.withdrawable_balance, Decimal("1"))
        self.assertEqual(self.wallet.withdraw_frozen, Decimal("4"))

    def test_cancel_and_reject_strictly_unfreeze_once(self):
        order = self._create()
        cancel_withdrawal(self.db, order, self.user)
        self.db.refresh(self.wallet)
        self.db.refresh(order)
        self.assertEqual(order.status, "canceled")
        self.assertEqual(self.wallet.balance, Decimal("10"))
        self.assertEqual(self.wallet.withdrawable_balance, Decimal("5"))
        self.assertEqual(self.wallet.withdraw_frozen, Decimal("0"))
        with self.assertRaisesRegex(BizError, "状态已变化"):
            cancel_withdrawal(self.db, order, self.user)
        self.db.refresh(self.wallet)
        self.assertEqual(self.wallet.balance, Decimal("10"))
        self.assertEqual(self.db.query(Ledger).filter(Ledger.type == "withdraw_unfreeze").count(), 1)

        other = self._create(request_id="withdraw-reject-0002")
        reject_withdrawal(self.db, other, self.admin, "资料不一致")
        self.db.refresh(self.wallet)
        self.assertEqual(self.wallet.withdraw_frozen, Decimal("0"))

    def test_paid_requires_receipt_and_settles_frozen_without_second_outflow(self):
        order = self._create()
        approve_withdrawal(self.db, order, self.admin, "人工复核通过")
        self.db.refresh(order)
        self.assertEqual(order.status, "manual_payment_pending")

        content = png_bytes()
        mime, suffix = validate_receipt(content)
        path, digest = persist_receipt(content, order, suffix)
        revealed = self._reveal(order)
        with self.assertRaisesRegex(BizError, "不同管理员"):
            mark_paid(
                self.db,
                order,
                self.admin,
                receipt_path=path,
                original_name="bank-transfer.png",
                content_type=mime,
                size_bytes=len(content),
                sha256=digest,
                bank_reference="BANKREF-TEST-0001",
                paid_amount_cny=Decimal("2.00"),
                paid_at=utc_now().replace(tzinfo=timezone.utc),
                payee_confirmed=True,
                reveal_token=revealed["reveal_token"],
            )
        self.db.refresh(order)
        self.db.refresh(self.wallet)
        self.assertEqual(order.status, "manual_payment_pending")
        self.assertIsNone(order.paid_by)
        self.assertEqual(self.wallet.frozen, Decimal("2"))
        self.assertEqual(self.wallet.withdraw_frozen, Decimal("2"))
        self.assertEqual(self.db.query(PayoutReceipt).count(), 0)
        self.assertEqual(
            self.db.query(PaymentInstructionGrant).filter(
                PaymentInstructionGrant.used_at.isnot(None)
            ).count(),
            0,
        )
        with self.assertRaisesRegex(BizError, "核对收款人"):
            mark_paid(
                self.db,
                order,
                self.payer,
                receipt_path=path,
                original_name="bank-transfer.png",
                content_type=mime,
                size_bytes=len(content),
                sha256=digest,
                bank_reference="BANKREF-TEST-0001",
                paid_amount_cny=Decimal("2.00"),
                paid_at=utc_now().replace(tzinfo=timezone.utc),
                payee_confirmed=False,
                reveal_token=revealed["reveal_token"],
            )
        with self.assertRaisesRegex(BizError, "查看凭证"):
            mark_paid(
                self.db,
                order,
                self.payer,
                receipt_path=path,
                original_name="bank-transfer.png",
                content_type=mime,
                size_bytes=len(content),
                sha256=digest,
                bank_reference="BANKREF-TEST-0001",
                paid_amount_cny=Decimal("2.00"),
                paid_at=utc_now().replace(tzinfo=timezone.utc),
                payee_confirmed=True,
                reveal_token="fabricated-client-assertion",
            )
        with self.assertRaisesRegex(BizError, "其他财务经办人"):
            mark_paid(
                self.db,
                order,
                self.other_payer,
                receipt_path=path,
                original_name="bank-transfer.png",
                content_type=mime,
                size_bytes=len(content),
                sha256=digest,
                bank_reference="BANKREF-TEST-0001",
                paid_amount_cny=Decimal("2.00"),
                paid_at=utc_now().replace(tzinfo=timezone.utc),
                payee_confirmed=True,
                reveal_token=revealed["reveal_token"],
            )
        self.card.bank_name = "已变更的收款银行"
        self.db.commit()
        with self.assertRaisesRegex(BizError, "查看凭证"):
            mark_paid(
                self.db,
                order,
                self.payer,
                receipt_path=path,
                original_name="bank-transfer.png",
                content_type=mime,
                size_bytes=len(content),
                sha256=digest,
                bank_reference="BANKREF-TEST-0001",
                paid_amount_cny=Decimal("2.00"),
                paid_at=utc_now().replace(tzinfo=timezone.utc),
                payee_confirmed=True,
                reveal_token=revealed["reveal_token"],
            )
        self.card.bank_name = "测试银行"
        self.db.commit()
        expired_reveal = self._reveal(order)
        expired_grant = self.db.query(PaymentInstructionGrant).order_by(
            PaymentInstructionGrant.id.desc()
        ).first()
        expired_grant.expires_at = utc_now() - timedelta(seconds=1)
        self.db.commit()
        with self.assertRaisesRegex(BizError, "查看凭证"):
            mark_paid(
                self.db,
                order,
                self.payer,
                receipt_path=path,
                original_name="bank-transfer.png",
                content_type=mime,
                size_bytes=len(content),
                sha256=digest,
                bank_reference="BANKREF-TEST-0001",
                paid_amount_cny=Decimal("2.00"),
                paid_at=utc_now().replace(tzinfo=timezone.utc),
                payee_confirmed=True,
                reveal_token=expired_reveal["reveal_token"],
            )
        final_reveal = self._reveal(order)
        mark_paid(
            self.db,
            order,
            self.payer,
            receipt_path=path,
            original_name="bank-transfer.png",
            content_type=mime,
            size_bytes=len(content),
            sha256=digest,
            bank_reference="BANKREF-TEST-0001",
            paid_amount_cny=Decimal("2.00"),
            paid_at=utc_now().replace(tzinfo=timezone.utc),
            payee_confirmed=True,
            reveal_token=final_reveal["reveal_token"],
        )
        self.db.refresh(order)
        self.db.refresh(self.wallet)
        self.assertEqual(order.status, "paid")
        self.assertEqual(order.reviewed_by, self.admin.id)
        self.assertEqual(order.payout_actor_id, self.payer.id)
        self.assertEqual(order.paid_by, self.payer.id)
        self.assertEqual(self.wallet.balance, Decimal("8"))
        self.assertEqual(self.wallet.frozen, Decimal("0"))
        self.assertEqual(self.wallet.withdrawable_balance, Decimal("3"))
        self.assertEqual(self.wallet.withdraw_frozen, Decimal("0"))
        success_event = self.db.query(Ledger).filter(Ledger.type == "withdraw_success").one()
        self.assertEqual(success_event.direction, "internal")
        self.assertEqual(success_event.balance_after, Decimal("8"))
        self.assertEqual(self.db.query(PayoutReceipt).count(), 1)
        grant = self.db.query(PaymentInstructionGrant).filter(
            PaymentInstructionGrant.used_at.isnot(None)
        ).one()
        self.assertIsNotNone(grant.used_at)
        self.assertTrue(path.is_file())
        response = finance_router.withdrawal_receipt(order.id, self.admin, self.db)
        self.assertEqual(response.headers["cache-control"], "no-store")
        self.assertTrue(response.headers["content-disposition"].startswith("attachment;"))

    def test_mark_failed_unfreezes_after_approval(self):
        order = self._create()
        approve_withdrawal(self.db, order, self.admin, None)
        self.db.refresh(order)
        fail_withdrawal(self.db, order, self.admin, "收款信息有误")
        self.db.refresh(order)
        self.db.refresh(self.wallet)
        self.assertEqual(order.status, "failed")
        self.assertEqual(self.wallet.balance, Decimal("10"))
        self.assertEqual(self.wallet.withdrawable_balance, Decimal("5"))

    def test_claimed_payout_can_only_be_failed_by_its_payout_operator(self):
        order = self._create(request_id="withdraw-claimed-failure")
        approve_withdrawal(self.db, order, self.admin, None)
        self.db.refresh(order)
        self._reveal(order, self.payer)
        self.db.refresh(order)
        self.assertEqual(order.payout_actor_id, self.payer.id)

        with self.assertRaisesRegex(BizError, "其他财务经办人"):
            fail_withdrawal(self.db, order, self.other_payer, "经办人不可用")
        self.db.refresh(order)
        self.db.refresh(self.wallet)
        self.assertEqual(order.status, "manual_payment_pending")
        self.assertEqual(self.wallet.balance, Decimal("8"))
        self.assertEqual(self.wallet.frozen, Decimal("2"))
        self.assertEqual(self.wallet.withdrawable_balance, Decimal("3"))
        self.assertEqual(self.wallet.withdraw_frozen, Decimal("2"))

        fail_withdrawal(self.db, order, self.payer, "银行侧转账未执行")
        self.db.refresh(order)
        self.db.refresh(self.wallet)
        self.assertEqual(order.status, "failed")
        self.assertEqual(order.reviewed_by, self.admin.id)
        self.assertEqual(order.payout_actor_id, self.payer.id)
        self.assertEqual(self.wallet.balance, Decimal("10"))
        self.assertEqual(self.wallet.frozen, Decimal("0"))
        self.assertEqual(self.wallet.withdrawable_balance, Decimal("5"))
        self.assertEqual(self.wallet.withdraw_frozen, Decimal("0"))

    def test_bank_reference_is_unique(self):
        first = self._create(amount="1", request_id="withdraw-ref-0001")
        approve_withdrawal(self.db, first, self.admin, None)
        self.db.refresh(first)
        content = png_bytes()
        mime, suffix = validate_receipt(content)
        path, digest = persist_receipt(content, first, suffix)
        first_reveal = self._reveal(first)
        mark_paid(
            self.db, first, self.payer,
            receipt_path=path, original_name="one.png", content_type=mime,
            size_bytes=len(content), sha256=digest,
            bank_reference="UNIQUE-REF-1", paid_amount_cny=Decimal("1.00"), paid_at=utc_now().replace(tzinfo=timezone.utc),
            payee_confirmed=True,
            reveal_token=first_reveal["reveal_token"],
        )
        second = self._create(amount="1", request_id="withdraw-ref-0002")
        approve_withdrawal(self.db, second, self.admin, None)
        self.db.refresh(second)
        path2, digest2 = persist_receipt(content, second, suffix)
        second_reveal = self._reveal(second)
        with self.assertRaisesRegex(BizError, "流水号已用于"):
            mark_paid(
                self.db, second, self.payer,
                receipt_path=path2, original_name="two.png", content_type=mime,
                size_bytes=len(content), sha256=digest2,
                bank_reference="UNIQUE-REF-1", paid_amount_cny=Decimal("1.00"), paid_at=utc_now().replace(tzinfo=timezone.utc),
                payee_confirmed=True,
                reveal_token=second_reveal["reveal_token"],
            )

    def test_receipt_magic_and_size_validation(self):
        with self.assertRaises(BizError):
            validate_receipt(b"not really png")
        with self.assertRaises(BizError):
            validate_receipt(b"%PDF-1.7\nmissing eof")
        settings.PAYOUT_RECEIPT_MAX_BYTES = 10
        with self.assertRaisesRegex(BizError, "5MB"):
            validate_receipt(png_bytes())

    def test_audit_log_never_accepts_card_shaped_digits(self):
        with self.assertRaisesRegex(BizError, "不得包含"):
            from app.services.manual_payout import record_audit
            record_audit(
                self.db, self.admin.id, "test", "withdrawal", 1,
                {"note": VALID_CARD},
            )

    def test_legacy_fake_withdraw_routes_are_non_mutating(self):
        before = Decimal(self.wallet.balance)
        with self.assertRaises(BizError) as wallet_error:
            wallet_router.withdraw(wallet_router.WithdrawInV2(amount=1, bank_card_id=self.card.id), self.user, self.db)
        self.assertEqual(wallet_error.exception.status_code, 410)
        with self.assertRaises(BizError) as supplier_error:
            supplier_router.supplier_withdraw({"amount": 1}, self.user, self.db)
        self.assertEqual(supplier_error.exception.status_code, 410)
        self.db.refresh(self.wallet)
        self.assertEqual(self.wallet.balance, before)


class ManualPayoutConcurrencyTests(unittest.TestCase):
    def test_two_sessions_cannot_freeze_same_funds(self):
        with tempfile.TemporaryDirectory() as tempdir:
            database = Path(tempdir) / "concurrency.db"
            engine = create_engine(
                f"sqlite:///{database}",
                connect_args={"check_same_thread": False, "timeout": 10},
            )
            Base.metadata.create_all(engine)
            Session = sessionmaker(bind=engine, expire_on_commit=False)
            setup = Session()
            user = User(phone="13900001991", username="并发用户", password="!")
            setup.add(user)
            setup.flush()
            wallet = Wallet(
                user_id=user.id, balance=Decimal("15"), frozen=Decimal("0"),
                withdrawable_balance=Decimal("15"), withdraw_frozen=Decimal("0"),
            )
            card = BankCard(
                user_id=user.id, bank_name="测试银行", card_number=VALID_CARD,
                holder="张三", status="active", verification_mode="manual_review",
                consent_at=datetime(2026, 8, 20, 8, 0, 0),
                consent_version=BANK_CARD_SENSITIVE_CONSENT_VERSION,
            )
            verification = Verification(
                user_id=user.id, real_name="张三", id_card="11010519491231002X",
                status="verified", front_photo="front.png", back_photo="back.png",
                consent_at=datetime(2026, 8, 20, 8, 0, 0),
            )
            setup.add_all([wallet, card, verification])
            setup.commit()
            user_id, card_id = user.id, card.id
            setup.close()

            original = {
                "DIRECT_TRADE_ENABLED": settings.DIRECT_TRADE_ENABLED,
                "MANUAL_PAYOUT_ENABLED": settings.MANUAL_PAYOUT_ENABLED,
                "PAYOUT_MIN_CARD_HOURS": settings.PAYOUT_MIN_CARD_HOURS,
                "SECRET_KEY": settings.SECRET_KEY,
                "SENSITIVE_DATA_KEY": settings.SENSITIVE_DATA_KEY,
            }
            settings.SECRET_KEY = "unit-test-manual-payout-concurrency-secret"
            settings.SENSITIVE_DATA_KEY = Fernet.generate_key().decode("ascii")
            settings.DIRECT_TRADE_ENABLED = True
            settings.MANUAL_PAYOUT_ENABLED = True
            settings.PAYOUT_MIN_CARD_HOURS = 10
            barrier = threading.Barrier(2)

            def attempt(request_id: str) -> str:
                db = Session()
                try:
                    local_user = db.query(User).filter(User.id == user_id).one()
                    barrier.wait(timeout=5)
                    create_withdrawal(
                        db, local_user, amount_card_hours=Decimal("10"),
                        bank_card_id=card_id, client_request_id=request_id,
                    )
                    return "ok"
                except BizError as exc:
                    if "可提现余额不足" in str(exc):
                        return "insufficient"
                    raise
                finally:
                    db.close()

            try:
                with ThreadPoolExecutor(max_workers=2) as pool:
                    results = list(pool.map(attempt, ("concurrent-request-1", "concurrent-request-2")))
            finally:
                for name, value in original.items():
                    setattr(settings, name, value)
            self.assertEqual(sorted(results), ["insufficient", "ok"])
            check = Session()
            final_wallet = check.query(Wallet).filter(Wallet.user_id == user_id).one()
            self.assertEqual(final_wallet.withdrawable_balance, Decimal("5"))
            self.assertEqual(final_wallet.withdraw_frozen, Decimal("10"))
            self.assertEqual(check.query(WithdrawalOrder).count(), 1)
            check.close()
            engine.dispose()

    def test_concurrent_reveal_claims_exactly_one_payout_operator(self):
        with tempfile.TemporaryDirectory() as tempdir:
            database = Path(tempdir) / "payout-claim.db"
            engine = create_engine(
                f"sqlite:///{database}",
                connect_args={"check_same_thread": False, "timeout": 10},
            )
            Base.metadata.create_all(engine)
            Session = sessionmaker(bind=engine, expire_on_commit=False)
            setup = Session()
            owner = User(phone="13900001801", username="提现用户", password="!")
            approver = User(
                phone="13900001802", username="审批管理员", password="!", role="admin",
            )
            payer_b = User(
                phone="13900001803", username="财务经办 B", password="!", role="admin",
            )
            payer_c = User(
                phone="13900001804", username="财务经办 C", password="!", role="admin",
            )
            setup.add_all([owner, approver, payer_b, payer_c])
            setup.flush()
            wallet = Wallet(
                user_id=owner.id,
                balance=Decimal("10"),
                frozen=Decimal("2"),
                withdrawable_balance=Decimal("3"),
                withdraw_frozen=Decimal("2"),
            )
            card = BankCard(
                user_id=owner.id,
                bank_name="测试银行",
                card_number=VALID_CARD,
                holder="张三",
                phone="13900001801",
                status="registered",
                verification_mode="format_only",
                consent_at=datetime(2026, 8, 20, 8, 0, 0),
                consent_version=BANK_CARD_SENSITIVE_CONSENT_VERSION,
            )
            setup.add_all([wallet, card])
            setup.flush()
            order = WithdrawalOrder(
                order_no="WODW-CONCURRENT-PAYOUT-CLAIM",
                user_id=owner.id,
                wallet_id=wallet.id,
                bank_card_id=card.id,
                client_request_id="concurrent-payout-claim",
                status="manual_payment_pending",
                amount_card_hours=Decimal("2"),
                locked_rate_cny=Decimal("1"),
                gross_amount_cny=Decimal("2"),
                fee_cny=Decimal("0"),
                net_amount_cny=Decimal("2"),
                bank_name_snapshot=card.bank_name,
                card_last4_snapshot=VALID_CARD[-4:],
                holder_snapshot=card.holder,
                reviewed_by=approver.id,
                reviewed_at=utc_now(),
                version=2,
            )
            setup.add(order)
            setup.commit()
            order_id = order.id
            approver_id = approver.id
            payer_ids = (payer_b.id, payer_c.id)
            setup.close()

            original = {
                "SECRET_KEY": settings.SECRET_KEY,
                "SENSITIVE_DATA_KEY": settings.SENSITIVE_DATA_KEY,
            }
            settings.SECRET_KEY = "unit-test-payout-actor-claim-secret"
            settings.SENSITIVE_DATA_KEY = Fernet.generate_key().decode("ascii")
            barrier = threading.Barrier(2)

            def reveal(actor_id: int) -> tuple[str, int, str]:
                db = Session()
                try:
                    actor = db.query(User).filter(User.id == actor_id).one()
                    barrier.wait(timeout=5)
                    try:
                        data = finance_router.payment_instructions(
                            order_id, Response(), True, actor, db,
                        )["data"]
                        return "ok", actor_id, data["reveal_token"]
                    except BizError as exc:
                        return "rejected", actor_id, str(exc)
                finally:
                    db.close()

            try:
                with ThreadPoolExecutor(max_workers=2) as pool:
                    results = list(pool.map(reveal, payer_ids))
            finally:
                for name, value in original.items():
                    setattr(settings, name, value)

            winners = [row for row in results if row[0] == "ok"]
            rejected = [row for row in results if row[0] == "rejected"]
            self.assertEqual(len(winners), 1)
            self.assertEqual(len(rejected), 1)
            self.assertIn("其他财务经办人", rejected[0][2])

            check = Session()
            final_order = check.query(WithdrawalOrder).filter(
                WithdrawalOrder.id == order_id
            ).one()
            winner_id = winners[0][1]
            loser_id = rejected[0][1]
            self.assertEqual(final_order.reviewed_by, approver_id)
            self.assertNotEqual(winner_id, approver_id)
            self.assertEqual(final_order.payout_actor_id, winner_id)
            self.assertEqual(
                check.query(PaymentInstructionGrant).filter(
                    PaymentInstructionGrant.withdrawal_id == order_id
                ).count(),
                1,
            )
            loser = check.query(User).filter(User.id == loser_id).one()
            with self.assertRaisesRegex(BizError, "其他财务经办人"):
                mark_paid(
                    check,
                    final_order,
                    loser,
                    receipt_path=Path(tempdir) / "not-written.png",
                    original_name="not-written.png",
                    content_type="image/png",
                    size_bytes=1,
                    sha256="0" * 64,
                    bank_reference="CONCURRENT-LOSER-REF",
                    paid_amount_cny=Decimal("2"),
                    paid_at=utc_now().replace(tzinfo=timezone.utc),
                    payee_confirmed=True,
                    reveal_token=winners[0][2],
                )
            check.refresh(final_order)
            self.assertEqual(final_order.status, "manual_payment_pending")
            self.assertIsNone(final_order.paid_by)
            check.close()
            engine.dispose()


class ManualPayoutMigrationTests(unittest.TestCase):
    def setUp(self):
        self.original_sensitive_settings = {
            "SECRET_KEY": settings.SECRET_KEY,
            "SENSITIVE_DATA_KEY": settings.SENSITIVE_DATA_KEY,
        }
        settings.SECRET_KEY = "unit-test-manual-payout-migration-secret"
        settings.SENSITIVE_DATA_KEY = Fernet.generate_key().decode("ascii")

    def tearDown(self):
        for name, value in self.original_sensitive_settings.items():
            setattr(settings, name, value)

    def _active_payout_with_grants(self, grant_count: int):
        engine = create_engine(
            "sqlite://",
            connect_args={"check_same_thread": False},
            poolclass=StaticPool,
        )
        Base.metadata.create_all(engine)
        db = sessionmaker(bind=engine, expire_on_commit=False)()
        owner = User(phone="13900001701", username="迁移提现用户", password="!")
        approver = User(
            phone="13900001702", username="迁移审批人", password="!", role="admin",
        )
        payers = [
            User(
                phone=f"1390000170{index + 3}",
                username=f"迁移付款人 {index + 1}",
                password="!",
                role="admin",
            )
            for index in range(grant_count)
        ]
        db.add_all([owner, approver, *payers])
        db.flush()
        wallet = Wallet(
            user_id=owner.id,
            balance=Decimal("2"),
            frozen=Decimal("2"),
            withdrawable_balance=Decimal("0"),
            withdraw_frozen=Decimal("2"),
        )
        card = BankCard(
            user_id=owner.id,
            bank_name="测试银行",
            card_number=VALID_CARD,
            holder="张三",
            phone="13900001701",
            status="registered",
            verification_mode="format_only",
            consent_at=datetime(2026, 8, 20, 8, 0, 0),
            consent_version=BANK_CARD_SENSITIVE_CONSENT_VERSION,
        )
        db.add_all([wallet, card])
        db.flush()
        order = WithdrawalOrder(
            order_no=f"WODW-MIGRATION-GRANTS-{grant_count}",
            user_id=owner.id,
            wallet_id=wallet.id,
            bank_card_id=card.id,
            client_request_id=f"migration-grants-{grant_count}",
            status="manual_payment_pending",
            amount_card_hours=Decimal("2"),
            locked_rate_cny=Decimal("1"),
            gross_amount_cny=Decimal("2"),
            fee_cny=Decimal("0"),
            net_amount_cny=Decimal("2"),
            bank_name_snapshot=card.bank_name,
            card_last4_snapshot=VALID_CARD[-4:],
            holder_snapshot=card.holder,
            reviewed_by=approver.id,
            reviewed_at=utc_now(),
            version=2,
        )
        db.add(order)
        db.flush()
        for index, payer in enumerate(payers):
            db.add(PaymentInstructionGrant(
                token_hash=f"{index + 1:064x}",
                actor_user_id=payer.id,
                withdrawal_id=order.id,
                bank_card_id=card.id,
                order_version=order.version,
                card_snapshot_hash=f"{index + 11:064x}",
                expires_at=utc_now() + timedelta(minutes=5),
            ))
        db.commit()
        return engine, db, order, payers

    def test_legacy_schema_adds_payout_actor_column(self):
        engine = create_engine("sqlite://")
        with engine.begin() as conn:
            conn.execute(text("CREATE TABLE withdrawal_orders (id INTEGER PRIMARY KEY)"))
        _ensure_columns(engine)
        columns = {column["name"] for column in inspect(engine).get_columns("withdrawal_orders")}
        self.assertIn("payout_actor_id", columns)
        engine.dispose()

    def test_unique_historical_reveal_actor_is_backfilled(self):
        engine, db, order, payers = self._active_payout_with_grants(1)
        _migrate_manual_payout_fields(engine, db)
        db.refresh(order)
        self.assertEqual(order.payout_actor_id, payers[0].id)
        db.close()
        engine.dispose()

    def test_multiple_historical_reveal_actors_stop_migration(self):
        engine, db, order, _payers = self._active_payout_with_grants(2)
        with self.assertRaisesRegex(RuntimeError, "multiple historical payout operators"):
            _migrate_manual_payout_fields(engine, db)
        db.refresh(order)
        self.assertIsNone(order.payout_actor_id)
        db.close()
        engine.dispose()

    def test_historical_money_never_becomes_withdrawable_and_sensitive_phone_is_encrypted(self):
        engine = create_engine(
            "sqlite://",
            connect_args={"check_same_thread": False},
            poolclass=StaticPool,
        )
        Base.metadata.create_all(engine)
        Session = sessionmaker(bind=engine, expire_on_commit=False)
        db = Session()
        user = User(phone="13900001992", username="迁移用户", password="!")
        db.add(user)
        db.flush()
        wallet = Wallet(
            user_id=user.id,
            balance=Decimal("99"),
            frozen=Decimal("0"),
            withdrawable_balance=Decimal("0"),
            withdraw_frozen=Decimal("0"),
        )
        card = BankCard(
            user_id=user.id,
            bank_name="历史银行",
            card_number=VALID_CARD,
            holder="张三",
            phone="13900001992",
            is_default=True,
            status="active",
            verification_mode="manual_review",
        )
        invalid_format = BankCard(
            user_id=user.id,
            bank_name="历史错误格式",
            card_number="4539-5787-6362-1486",
            holder="张三",
            is_default=True,
            status="pending_review",
            verification_mode="manual_review",
        )
        invalid_luhn = BankCard(
            user_id=user.id,
            bank_name="历史校验失败",
            card_number="4539578763621487",
            holder="张三",
            status="active",
            verification_mode="manual_review",
        )
        db.add_all([wallet, card, invalid_format, invalid_luhn])
        db.flush()
        db.add_all([
            Ledger(
                user_id=user.id, wallet_id=wallet.id, type="recharge", direction="in",
                amount=Decimal("50"), balance_after=Decimal("50"),
            ),
            Ledger(
                user_id=user.id, wallet_id=wallet.id, type="revenue", direction="in",
                amount=Decimal("49"), balance_after=Decimal("99"),
            ),
        ])
        db.commit()
        # Historical recharge/revenue ledger rows exist, but the migration must
        # not derive any withdrawable value from them.
        _migrate_manual_payout_fields(engine, db)
        _migrate_sensitive_fields(db)
        db.refresh(wallet)
        db.refresh(card)
        db.refresh(invalid_format)
        db.refresh(invalid_luhn)
        self.assertEqual(wallet.withdrawable_balance, Decimal("0"))
        self.assertEqual(wallet.withdraw_frozen, Decimal("0"))
        self.assertEqual(card.status, "registered")
        self.assertEqual(card.verification_mode, "format_only")
        self.assertTrue(card.is_default)
        self.assertIsNotNone(card.card_fingerprint)
        self.assertTrue(card.card_number.startswith("enc:v1:"))
        self.assertTrue(card.phone.startswith("enc:v1:"))
        self.assertEqual(reveal(card.phone), "13900001992")
        for invalid in (invalid_format, invalid_luhn):
            self.assertEqual(invalid.status, "disabled")
            self.assertEqual(invalid.verification_mode, "legacy_unvalidated")
            self.assertFalse(invalid.is_default)
            self.assertIsNone(invalid.card_fingerprint)
            self.assertIn("Luhn", invalid.review_reason)
        db.close()
        engine.dispose()


if __name__ == "__main__":
    unittest.main()
