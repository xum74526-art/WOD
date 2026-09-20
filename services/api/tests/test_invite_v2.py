import tempfile
import unittest
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from pathlib import Path

from cryptography.fernet import Fernet
from sqlalchemy import create_engine, inspect, text
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.core.config import settings
from app.core.sensitive import SensitiveDataDecryptionError
from app.db.base import Base
from app.models import *  # noqa: F401,F403 - register complete test metadata
from app.models.invite import InviteCode, InviteDailyQuota, InviteRecord
from app.models.ledger import Ledger
from app.models.order import Order
from app.models.order_funding import OrderFundingAllocation
from app.models.order_renewal import OrderRenewal
from app.models.product import Product
from app.models.reward_accrual import RewardAccrual
from app.models.user import User
from app.models.verification import Verification
from app.models.wallet import Wallet
from app.routers.finance import verification_review
from app.routers.invite import create_invite_relationship, records, summary
from app.schemas.invite import InviteRelationshipListResponse, InviteSummaryResponse
from app.schemas.withdrawal import FinanceReviewIn
from app.services.funding_allocation import (
    capture_order_funding,
    refund_order_funding,
    reserve_order_funding,
    spend_renewal_funding,
)
from app.services.invite_rewards_v2 import (
    INVITE_V2_POLICY_VERSION,
    INVITE_V2_RELATIONSHIP_VERSION,
    STATUS_DAILY_CAP_EXCEEDED,
    STATUS_PENDING_IDENTITY,
    STATUS_QUALIFIED,
    STATUS_RISK_REJECTED,
    STATUS_RISK_REVIEW,
    process_invite_order_event,
    process_invite_renewal_event,
    reevaluate_invitee_qualification,
)
from app.services.reward_program import (
    PROGRAM_INVITE_COMMISSION,
    PROGRAM_INVITE_QUALIFICATION,
    assert_reward_configuration_safe,
)
from init_db import _ensure_columns, _migrate_invite_v2_funding_fields


class InviteV2Tests(unittest.TestCase):
    SWITCHES = (
        "REWARD_SERVICE_ENABLED",
        "CLOSED_TEST_REWARD_ENABLED",
        "INVITE_REWARD_ENABLED",
        "INVITE_V2_ENABLED",
        "REWARD_SETTLEMENT_ENABLED",
    )

    def setUp(self):
        self.original_switches = {name: getattr(settings, name) for name in self.SWITCHES}
        self.original_sensitive_settings = {
            "SECRET_KEY": settings.SECRET_KEY,
            "SENSITIVE_DATA_KEY": settings.SENSITIVE_DATA_KEY,
        }
        for name in self.SWITCHES:
            setattr(settings, name, False)
        settings.INVITE_V2_ENABLED = True
        settings.REWARD_SETTLEMENT_ENABLED = True
        settings.SECRET_KEY = "unit-test-invite-v2-secret"
        settings.SENSITIVE_DATA_KEY = Fernet.generate_key().decode("ascii")
        self.engine = create_engine(
            "sqlite://",
            connect_args={"check_same_thread": False},
            poolclass=StaticPool,
        )
        Base.metadata.create_all(self.engine)
        self.db = sessionmaker(bind=self.engine, expire_on_commit=False)()
        self.now = datetime(2026, 8, 26, 2, 0, tzinfo=timezone.utc)
        self.sequence = 0

        self.inviter = User(
            username="v2-inviter", phone="13910000001", password="!", phone_bound=True
        )
        self.db.add(self.inviter)
        self.db.flush()
        self.db.add_all([
            Wallet(
                user_id=self.inviter.id,
                balance=Decimal("0"),
                frozen=Decimal("0"),
                promotional_balance=Decimal("0"),
                promotional_frozen=Decimal("0"),
                withdrawable_balance=Decimal("0"),
                withdraw_frozen=Decimal("0"),
            ),
            InviteCode(user_id=self.inviter.id, code="WODV2TEST", invited_count=0),
        ])
        self.product = Product(
            name="V2 GPU",
            gpu_model="H100",
            memory="80GB",
            price=Decimal("1"),
            cycle=[],
            stock=100,
            status="on",
        )
        self.db.add(self.product)
        self.db.commit()

    def tearDown(self):
        self.db.close()
        self.engine.dispose()
        for name, value in self.original_switches.items():
            setattr(settings, name, value)
        for name, value in self.original_sensitive_settings.items():
            setattr(settings, name, value)

    def test_summary_generates_ztw_code_for_account_without_invite_code(self):
        user = User(
            username="new-inviter",
            phone="13910000002",
            password="!",
            phone_bound=True,
        )
        self.db.add(user)
        self.db.commit()

        result = summary(user, self.db)["data"]

        self.assertRegex(result["code"], r"^ZTW[A-Z0-9]{6}$")
        self.assertEqual(
            self.db.query(InviteCode).filter(InviteCode.user_id == user.id).one().code,
            result["code"],
        )

    def _friend(self, *, verified: bool = True, id_card: str | None = None):
        self.sequence += 1
        user = User(
            username=f"friend-{self.sequence}",
            phone=f"1381{self.sequence:07d}",
            password="!",
            phone_bound=False,
            invited_by=self.inviter.id,
        )
        self.db.add(user)
        self.db.flush()
        wallet = Wallet(
            user_id=user.id,
            balance=Decimal("0"),
            frozen=Decimal("0"),
            promotional_balance=Decimal("0"),
            promotional_frozen=Decimal("0"),
            withdrawable_balance=Decimal("0"),
            withdraw_frozen=Decimal("0"),
        )
        self.db.add(wallet)
        record = create_invite_relationship(user, self.inviter.id, self.db, platform="web")
        if verified:
            self.db.add(Verification(
                user_id=user.id,
                real_name=f"用户{self.sequence}",
                id_card=id_card or f"11010119900101{self.sequence:04d}",
                status="verified",
            ))
        self.db.flush()
        return user, wallet, record

    def _complete_order(
        self,
        user: User,
        wallet: Wallet,
        *,
        gross: Decimal = Decimal("100"),
        promotional: Decimal = Decimal("0"),
        event_at: datetime | None = None,
    ):
        event_at = event_at or self.now
        wallet.balance = Decimal(str(gross))
        wallet.promotional_balance = Decimal(str(promotional))
        order = Order(
            order_no=f"INV2{user.id:08d}{self.sequence:04d}",
            user_id=user.id,
            product_id=self.product.id,
            quantity=1,
            purchase_hours=24,
            cycle_days=0,
            amount=gross,
            status="paid",
            purchase_type="usage",
            start_at=event_at,
        )
        self.db.add(order)
        self.db.flush()
        allocation = reserve_order_funding(order, wallet, gross, self.db)
        order.status = "completed"
        order.confirmed_at = event_at
        order.start_at = event_at
        order.end_at = event_at + timedelta(hours=24)
        capture_order_funding(order, wallet, self.db, captured_at=event_at)
        self.db.flush()
        accrual = process_invite_order_event(order, self.db, event_at=event_at)
        self.db.flush()
        return order, allocation, accrual

    def test_verified_first_cash_order_grants_58_to_inviter_promotional_only(self):
        friend, wallet, record = self._friend()
        order, allocation, commission = self._complete_order(friend, wallet)

        self.assertEqual(allocation.cash_amount, Decimal("100.000000"))
        self.assertEqual(record.qualification_status, STATUS_QUALIFIED)
        self.assertEqual(record.qualification_order_id, order.id)
        bonus = self.db.query(RewardAccrual).filter(
            RewardAccrual.program_code == PROGRAM_INVITE_QUALIFICATION,
            RewardAccrual.source_id == record.id,
        ).one()
        self.assertEqual(bonus.reward_amount, Decimal("58.000000"))
        self.assertEqual(bonus.status, "settled")
        self.assertIsNotNone(commission)
        self.assertEqual(commission.rate_bps, 0)
        inviter_wallet = self.db.query(Wallet).filter(Wallet.user_id == self.inviter.id).one()
        self.assertEqual(inviter_wallet.balance, Decimal("58.000000"))
        self.assertEqual(inviter_wallet.promotional_balance, Decimal("58.000000"))
        self.assertEqual(inviter_wallet.withdrawable_balance, Decimal("0.000000"))

        records_payload = records(page=1, page_size=50, user=self.inviter, db=self.db)
        parsed_records = InviteRelationshipListResponse.model_validate(records_payload)
        self.assertEqual(parsed_records.data.items[0].status, record.status)
        self.assertEqual(parsed_records.data.items[0].legacy_status, record.status)

        process_invite_order_event(order, self.db, event_at=self.now)
        self.assertEqual(self.db.query(RewardAccrual).filter(
            RewardAccrual.beneficiary_user_id == self.inviter.id,
        ).count(), 2)

    def test_order_first_then_finance_identity_review_grants_bonus_without_backdated_commission(self):
        friend, wallet, record = self._friend(verified=False)
        order, _, commission = self._complete_order(friend, wallet)
        self.assertIsNone(commission)
        self.assertEqual(record.qualification_status, STATUS_PENDING_IDENTITY)

        verification = Verification(
            user_id=friend.id,
            real_name="测试用户",
            id_card="110101199001011234",
            status="pending",
            consent_at=self.now,
            front_photo="front.jpg",
            back_photo="back.jpg",
        )
        actor = User(username="finance", phone="13919999999", password="!")
        self.db.add_all([verification, actor])
        self.db.flush()
        verification_review(
            verification.id,
            FinanceReviewIn(approved=True),
            actor,
            self.db,
            platform="admin",
        )
        self.db.refresh(record)
        self.assertEqual(record.qualification_status, STATUS_QUALIFIED)
        self.assertEqual(self.db.query(RewardAccrual).filter(
            RewardAccrual.program_code == PROGRAM_INVITE_QUALIFICATION,
            RewardAccrual.beneficiary_user_id == self.inviter.id,
        ).count(), 1)
        self.assertEqual(self.db.query(RewardAccrual).filter(
            RewardAccrual.program_code == PROGRAM_INVITE_COMMISSION,
            RewardAccrual.order_id == order.id,
        ).count(), 0)

    def test_daily_sixth_relation_is_retained_but_never_qualified(self):
        records = []
        for _ in range(6):
            friend, wallet, record = self._friend()
            self._complete_order(friend, wallet, event_at=self.now)
            records.append(record)
        self.assertEqual([row.qualification_status for row in records[:5]], [STATUS_QUALIFIED] * 5)
        self.assertEqual(records[5].qualification_status, STATUS_DAILY_CAP_EXCEEDED)
        self.assertIsNone(records[5].fixed_reward_accrual_id)
        quota = self.db.query(InviteDailyQuota).one()
        self.assertEqual(quota.used_count, 5)
        self.assertEqual(self.db.query(InviteRecord).filter(
            InviteRecord.inviter_id == self.inviter.id,
        ).count(), 6)

    def test_tier_boundaries_use_post_qualification_count_and_cash_only_base(self):
        boundary_rates = {}
        for index in range(1, 21):
            event_at = self.now + timedelta(days=(index - 1) // 5)
            friend, wallet, _ = self._friend()
            _, allocation, accrual = self._complete_order(
                friend,
                wallet,
                gross=Decimal("100"),
                promotional=Decimal("40") if index == 5 else Decimal("0"),
                event_at=event_at,
            )
            if index == 5:
                self.assertEqual(allocation.cash_amount, Decimal("60.000000"))
                self.assertEqual(accrual.base_amount, Decimal("60.000000"))
            if index in {5, 10, 15, 20}:
                boundary_rates[index] = accrual.rate_bps
        self.assertEqual(boundary_rates, {5: 200, 10: 400, 15: 600, 20: 800})

        payload = summary(self.inviter, self.db)
        parsed = InviteSummaryResponse.model_validate(payload)
        self.assertEqual(parsed.data.current_rate_bps, 800)
        self.assertEqual(parsed.data.qualified_count, 20)
        self.assertEqual(parsed.data.eligible_friend_spend_card_hours, 1960.0)
        self.assertFalse(parsed.data.rewards_withdrawable)
        self.assertFalse(parsed.data.rewards_transferable)

    def test_renewal_commission_uses_cash_split_and_is_idempotent(self):
        fifth = None
        for _ in range(5):
            friend, wallet, _ = self._friend()
            order, _, _ = self._complete_order(friend, wallet, event_at=self.now)
            fifth = (friend, wallet, order)
        friend, wallet, order = fifth
        renewal = OrderRenewal(
            order_id=order.id,
            user_id=friend.id,
            client_request_id="renew-invite-v2-0001",
            created_platform="web",
            purchase_hours=24,
            cycle_days=None,
            quantity=1,
            amount=Decimal("100"),
            previous_end_at=order.end_at,
            new_end_at=order.end_at + timedelta(hours=24),
            total_amount_after=Decimal(order.amount) + Decimal("100"),
            total_purchase_hours_after=48,
            total_cycle_days_after=None,
            response_payload={},
        )
        self.db.add(renewal)
        self.db.flush()
        wallet.balance = Decimal("100")
        wallet.promotional_balance = Decimal("30")
        spend_renewal_funding(
            order, renewal, wallet, Decimal("100"), self.db, captured_at=self.now
        )
        first = process_invite_renewal_event(
            order, renewal, self.db, event_at=self.now + timedelta(minutes=1)
        )
        second = process_invite_renewal_event(
            order, renewal, self.db, event_at=self.now + timedelta(minutes=1)
        )
        self.assertEqual(first.id, second.id)
        self.assertEqual(first.base_amount, Decimal("70.000000"))
        self.assertEqual(first.rate_bps, 200)
        self.assertEqual(first.reward_amount, Decimal("1.400000"))
        self.assertEqual(self.db.query(RewardAccrual).filter(
            RewardAccrual.program_code == PROGRAM_INVITE_COMMISSION,
            RewardAccrual.order_renewal_id == renewal.id,
        ).count(), 1)

    def test_same_identity_self_invite_and_decryption_failure_are_blocked(self):
        self.db.add(Verification(
            user_id=self.inviter.id,
            real_name="邀请人",
            id_card="110101199001011111",
            status="verified",
        ))
        same_user, _, same_record = self._friend(
            verified=True,
            id_card="110101199001011111",
        )
        reevaluate_invitee_qualification(same_user.id, self.db, event_at=self.now)
        self.assertEqual(same_record.qualification_status, STATUS_RISK_REJECTED)
        self.assertEqual(same_record.qualification_reason, "same_verified_identity")

        broken_user, _, broken_record = self._friend(
            verified=True,
            id_card="enc:v1:not-a-valid-token",
        )
        with self.assertRaises(SensitiveDataDecryptionError):
            reevaluate_invitee_qualification(broken_user.id, self.db, event_at=self.now)
        self.assertEqual(broken_record.qualification_status, STATUS_PENDING_IDENTITY)
        self.assertEqual(broken_record.qualification_reason, "verified_identity_required")

        self_user = User(
            username="self", phone="13918888888", password="!", invited_by=None
        )
        self.db.add(self_user)
        self.db.flush()
        self_user.invited_by = self_user.id
        self.db.add(Wallet(user_id=self_user.id, balance=0, frozen=0))
        self_record = InviteRecord(
            inviter_id=self_user.id,
            invitee_id=self_user.id,
            invitee_phone="139****8888",
            status="unverified",
            qualification_policy_version=INVITE_V2_RELATIONSHIP_VERSION,
            qualification_status=STATUS_PENDING_IDENTITY,
        )
        self.db.add(self_record)
        self.db.flush()
        reevaluate_invitee_qualification(self_user.id, self.db, event_at=self.now)
        self.assertEqual(self_record.qualification_status, STATUS_RISK_REJECTED)
        self.assertEqual(self_record.qualification_reason, "self_invite")

    def test_v1_or_disabled_relationship_is_not_upgraded_when_v2_turns_on(self):
        settings.INVITE_V2_ENABLED = False
        friend, wallet, record = self._friend()
        self.assertIsNone(record.qualification_policy_version)
        settings.INVITE_V2_ENABLED = True
        self._complete_order(friend, wallet)
        self.assertIsNone(record.qualification_policy_version)
        self.assertEqual(self.db.query(RewardAccrual).filter(
            RewardAccrual.program_code.in_((
                PROGRAM_INVITE_QUALIFICATION,
                PROGRAM_INVITE_COMMISSION,
            )),
        ).count(), 0)

    def test_startup_rejects_v1_and_v2_writers_together(self):
        settings.INVITE_REWARD_ENABLED = True
        with self.assertRaisesRegex(RuntimeError, "V1 and V2"):
            assert_reward_configuration_safe()


class InviteV2ConcurrencyTests(unittest.TestCase):
    def test_concurrent_sixth_qualification_cannot_overbook_daily_quota(self):
        original_v2 = settings.INVITE_V2_ENABLED
        original_settlement = settings.REWARD_SETTLEMENT_ENABLED
        settings.INVITE_V2_ENABLED = True
        settings.REWARD_SETTLEMENT_ENABLED = False
        try:
            with tempfile.TemporaryDirectory() as temp_dir:
                engine = create_engine(
                    f"sqlite:///{Path(temp_dir) / 'quota.sqlite3'}",
                    connect_args={"check_same_thread": False, "timeout": 20},
                )
                Base.metadata.create_all(engine)
                factory = sessionmaker(bind=engine, expire_on_commit=False)
                event_at = datetime(2026, 8, 26, 3, 0, tzinfo=timezone.utc)
                invitee_ids = []
                with factory() as db:
                    inviter = User(username="concurrent-inviter", phone="13710000001", password="!")
                    product = Product(
                        name="Concurrent GPU", gpu_model="H100", memory="80GB",
                        price=1, cycle=[], stock=10, status="on",
                    )
                    db.add_all([inviter, product])
                    db.flush()
                    db.add_all([
                        Wallet(user_id=inviter.id, balance=0, frozen=0),
                        InviteCode(user_id=inviter.id, code="WODCONCUR", invited_count=0),
                    ])
                    for index in range(6):
                        friend = User(
                            username=f"concurrent-{index}",
                            phone=f"1372{index:07d}",
                            password="!",
                            invited_by=inviter.id,
                        )
                        db.add(friend)
                        db.flush()
                        wallet = Wallet(user_id=friend.id, balance=100, frozen=0)
                        record = InviteRecord(
                            inviter_id=inviter.id,
                            invitee_id=friend.id,
                            invitee_phone=f"137****{index:04d}",
                            status="unverified",
                            qualification_policy_version=INVITE_V2_RELATIONSHIP_VERSION,
                            qualification_status=STATUS_PENDING_IDENTITY,
                        )
                        verification = Verification(
                            user_id=friend.id,
                            real_name=f"并发{index}",
                            id_card=f"11010119910101{index:04d}",
                            status="verified",
                        )
                        db.add_all([wallet, record, verification])
                        db.flush()
                        order = Order(
                            order_no=f"CONCURRENT{index:06d}",
                            user_id=friend.id,
                            product_id=product.id,
                            amount=Decimal("100"),
                            status="paid",
                            purchase_type="usage",
                            start_at=event_at,
                        )
                        db.add(order)
                        db.flush()
                        reserve_order_funding(order, wallet, Decimal("100"), db)
                        order.status = "completed"
                        order.confirmed_at = event_at
                        capture_order_funding(order, wallet, db, captured_at=event_at)
                        invitee_ids.append(friend.id)
                    db.commit()

                def qualify(invitee_id: int) -> str:
                    with factory() as db:
                        row = reevaluate_invitee_qualification(
                            invitee_id, db, event_at=event_at
                        )
                        db.commit()
                        return row.qualification_status

                with ThreadPoolExecutor(max_workers=6) as executor:
                    statuses = list(executor.map(qualify, invitee_ids))
                self.assertEqual(statuses.count(STATUS_QUALIFIED), 5)
                self.assertEqual(statuses.count(STATUS_DAILY_CAP_EXCEEDED), 1)
                with factory() as db:
                    quota = db.query(InviteDailyQuota).one()
                    self.assertEqual(quota.used_count, 5)
                    self.assertEqual(db.query(RewardAccrual).filter(
                        RewardAccrual.program_code == PROGRAM_INVITE_QUALIFICATION,
                    ).count(), 5)
                engine.dispose()
        finally:
            settings.INVITE_V2_ENABLED = original_v2
            settings.REWARD_SETTLEMENT_ENABLED = original_settlement


class FundingMigrationTests(unittest.TestCase):
    def test_legacy_invite_columns_use_date_and_duplicate_relationships_fail_closed(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            engine = create_engine(f"sqlite:///{Path(temp_dir) / 'legacy.sqlite3'}")
            with engine.begin() as conn:
                conn.execute(text(
                    "CREATE TABLE invite_records ("
                    "id INTEGER PRIMARY KEY, inviter_id INTEGER, invitee_id INTEGER, "
                    "invitee_phone TEXT, status TEXT, reward_amount NUMERIC, "
                    "created_platform TEXT, last_modified_platform TEXT)"
                ))
                conn.execute(text(
                    "CREATE TABLE wallets ("
                    "id INTEGER PRIMARY KEY, user_id INTEGER, balance NUMERIC, frozen NUMERIC, "
                    "withdrawable_balance NUMERIC, withdraw_frozen NUMERIC, "
                    "promotional_balance NUMERIC, promotional_frozen NUMERIC)"
                ))
            _ensure_columns(engine)
            column_types = {
                row["name"]: row["type"].__class__.__name__.upper()
                for row in inspect(engine).get_columns("invite_records")
            }
            self.assertEqual(column_types["qualification_day"], "DATE")
            with engine.begin() as conn:
                conn.execute(text(
                    "INSERT INTO invite_records "
                    "(id, inviter_id, invitee_id, invitee_phone, status) VALUES "
                    "(1, 1, 9, 'x', 'registered'), (2, 2, 9, 'x', 'registered')"
                ))
            with self.assertRaisesRegex(RuntimeError, "duplicate invite relationships"):
                _migrate_invite_v2_funding_fields(engine)
            with engine.connect() as conn:
                self.assertEqual(conn.execute(text(
                    "SELECT COUNT(*) FROM invite_records WHERE invitee_id = 9"
                )).scalar_one(), 2)
            engine.dispose()

    def test_historical_reward_upper_bound_and_frozen_are_promotional(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            engine = create_engine(
                f"sqlite:///{Path(temp_dir) / 'migration.sqlite3'}",
                connect_args={"check_same_thread": False},
            )
            Base.metadata.create_all(engine)
            factory = sessionmaker(bind=engine, expire_on_commit=False)
            with factory() as db:
                user = User(username="legacy", phone="13917770001", password="!")
                db.add(user)
                db.flush()
                wallet = Wallet(
                    user_id=user.id,
                    balance=Decimal("150"),
                    frozen=Decimal("30"),
                    withdrawable_balance=Decimal("10"),
                    promotional_balance=Decimal("0"),
                    promotional_frozen=Decimal("0"),
                )
                db.add(wallet)
                db.flush()
                db.add_all([
                    Ledger(
                        user_id=user.id,
                        wallet_id=wallet.id,
                        type="consumer_purchase_rebate",
                        direction="in",
                        amount=Decimal("80"),
                        balance_after=Decimal("80"),
                    ),
                    Ledger(
                        user_id=user.id,
                        wallet_id=wallet.id,
                        type="test_invite",
                        direction="in",
                        amount=Decimal("40"),
                        balance_after=Decimal("120"),
                    ),
                ])
                db.commit()

            result = _migrate_invite_v2_funding_fields(engine)
            self.assertEqual(result["wallets_backfilled"], 1)
            with factory() as db:
                wallet = db.query(Wallet).one()
                # Spendable = 150 - 10 withdrawable - 40 excluded legacy = 100.
                # Reward history upper bound is 120, so the conservative clamp is 100.
                self.assertEqual(wallet.promotional_balance, Decimal("100.000000"))
                self.assertEqual(wallet.promotional_frozen, Decimal("30.000000"))
            self.assertEqual(
                _migrate_invite_v2_funding_fields(engine)["wallets_backfilled"],
                0,
            )
            indexes = {row["name"] for row in inspect(engine).get_indexes("invite_records")}
            self.assertIn("ix_invite_records_invitee_unique", indexes)
            engine.dispose()

    def test_multiple_legacy_frozen_orders_claim_preclassified_pool_once(self):
        engine = create_engine(
            "sqlite://",
            connect_args={"check_same_thread": False},
            poolclass=StaticPool,
        )
        Base.metadata.create_all(engine)
        db = sessionmaker(bind=engine, expire_on_commit=False)()
        user = User(username="legacy-orders", phone="13917770002", password="!")
        product = Product(
            name="Legacy GPU", gpu_model="A100", memory="80GB",
            price=1, cycle=[], stock=1, status="on",
        )
        db.add_all([user, product])
        db.flush()
        wallet = Wallet(
            user_id=user.id,
            balance=Decimal("0"),
            frozen=Decimal("30"),
            promotional_balance=Decimal("0"),
            promotional_frozen=Decimal("30"),
        )
        db.add(wallet)
        db.flush()
        first = Order(
            order_no="LEGACYFROZEN1", user_id=user.id, product_id=product.id,
            amount=Decimal("10"), status="delivering", purchase_type="usage",
        )
        second = Order(
            order_no="LEGACYFROZEN2", user_id=user.id, product_id=product.id,
            amount=Decimal("20"), status="paid", purchase_type="usage",
        )
        db.add_all([first, second])
        db.flush()

        capture_order_funding(first, wallet, db)
        refund_order_funding(second, wallet, db)
        self.assertEqual(wallet.frozen, Decimal("0.000000"))
        self.assertEqual(wallet.promotional_frozen, Decimal("0.000000"))
        self.assertEqual(wallet.balance, Decimal("20.000000"))
        self.assertEqual(wallet.promotional_balance, Decimal("20.000000"))
        allocations = db.query(OrderFundingAllocation).order_by(
            OrderFundingAllocation.order_id.asc()
        ).all()
        self.assertEqual([row.promotional_amount for row in allocations], [
            Decimal("10.000000"), Decimal("20.000000")
        ])
        self.assertEqual([row.cash_amount for row in allocations], [
            Decimal("0.000000"), Decimal("0.000000")
        ])
        db.close()
        engine.dispose()
