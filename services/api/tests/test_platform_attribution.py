import unittest
from decimal import Decimal

from cryptography.fernet import Fernet
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.core.config import settings
from app.db.base import Base
from app.models import (
    BankCard,
    PaymentOrder,
    Post,
    User,
    Verification,
    Wallet,
    WithdrawalOrder,
)  # noqa: F401
from app.models.invite import InviteRecord  # noqa: F401
from app.routers import bank_card as bank_card_router
from app.routers import community as community_router
from app.routers import verification as verification_router
from app.routers.invite import create_invite_relationship
from app.schemas.bank_card import BankCardIn
from app.schemas.community import PostCreateIn
from app.schemas.verification import VerificationIn
from app.services.manual_payout import approve_withdrawal, create_withdrawal
from app.services.qixiangpay import create_recharge_order


class PlatformAttributionTests(unittest.TestCase):
    def setUp(self):
        engine = create_engine(
            "sqlite://",
            connect_args={"check_same_thread": False},
            poolclass=StaticPool,
        )
        Base.metadata.create_all(engine)
        self.db = sessionmaker(bind=engine)()
        self.user = User(phone="13900000001", username="来源用户", password="!")
        self.admin = User(
            phone="13900000002", username="来源管理员", password="!", role="admin"
        )
        self.db.add_all([self.user, self.admin])
        self.db.flush()
        self.wallet = Wallet(
            user_id=self.user.id,
            balance=Decimal("20"),
            frozen=Decimal("0"),
            withdrawable_balance=Decimal("10"),
            withdraw_frozen=Decimal("0"),
        )
        self.db.add(self.wallet)
        self.db.commit()
        names = (
            "SECRET_KEY",
            "SENSITIVE_DATA_KEY",
            "MANUAL_BANK_CARD_ENABLED",
            "MANUAL_PAYOUT_ENABLED",
            "DIRECT_TRADE_ENABLED",
            "PAYMENT_SERVICE_ENABLED",
            "QIXIANGPAY_ENABLED",
            "QIXIANGPAY_BASE_URL",
            "QIXIANGPAY_PID",
            "QIXIANGPAY_KEY",
            "QIXIANGPAY_NOTIFY_URL",
            "QIXIANGPAY_RETURN_URL",
            "QIXIANGPAY_PUBLIC_API_BASE_URL",
            "QIXIANGPAY_PAYMENT_TYPES",
        )
        self.original = {name: getattr(settings, name) for name in names}
        settings.SECRET_KEY = "unit-test-platform-attribution-secret"
        settings.SENSITIVE_DATA_KEY = Fernet.generate_key().decode("ascii")
        settings.MANUAL_BANK_CARD_ENABLED = True
        settings.MANUAL_PAYOUT_ENABLED = True
        settings.DIRECT_TRADE_ENABLED = True
        settings.PAYMENT_SERVICE_ENABLED = True
        settings.QIXIANGPAY_ENABLED = True
        settings.QIXIANGPAY_BASE_URL = "https://api.payqixiang.cn"
        settings.QIXIANGPAY_PID = "test-pid"
        settings.QIXIANGPAY_KEY = "test-key"
        settings.QIXIANGPAY_NOTIFY_URL = "https://wod.kai.com/api/payments/qixiang/notify"
        settings.QIXIANGPAY_RETURN_URL = "https://wod.kai.com/payment/qixiang/return"
        settings.QIXIANGPAY_PUBLIC_API_BASE_URL = "https://wod.kai.com/api"
        settings.QIXIANGPAY_PAYMENT_TYPES = "alipay"

    def tearDown(self):
        for name, value in self.original.items():
            setattr(settings, name, value)
        self.db.close()

    def test_payment_verification_card_and_withdrawal_keep_origin(self):
        payment = create_recharge_order(
            self.db,
            self.user.id,
            Decimal("10"),
            payment_type="alipay",
            created_platform="android",
        )
        payment_row = self.db.query(PaymentOrder).filter(
            PaymentOrder.order_no == payment["order_no"]
        ).one()
        self.assertEqual(payment_row.created_platform, "android")
        self.assertEqual(payment_row.last_modified_platform, "android")

        verification_router.submit(
            VerificationIn(
                real_name="张三",
                id_card="11010519491231002X",
                sensitive_consent=True,
            ),
            self.user,
            self.db,
            "ios",
        )
        verification = self.db.query(Verification).filter_by(user_id=self.user.id).one()
        self.assertEqual(verification.created_platform, "ios")
        verification.status = "verified"
        self.db.commit()

        card_output = bank_card_router.add_card(
            BankCardIn(
                bank_name="测试银行",
                card_number="4539578763621486",
                holder="张三",
                phone="13900000001",
                sensitive_consent=True,
            ),
            self.user,
            self.db,
            "android",
        )
        card = self.db.query(BankCard).filter(BankCard.id == card_output["data"]["id"]).one()
        self.assertEqual(card.created_platform, "android")

        withdrawal = create_withdrawal(
            self.db,
            self.user,
            amount_card_hours=Decimal("10"),
            bank_card_id=card.id,
            client_request_id="platform-withdrawal-0001",
            created_platform="web",
        )
        self.assertEqual(withdrawal.created_platform, "web")
        approve_withdrawal(
            self.db,
            withdrawal,
            self.admin,
            None,
            platform="admin",
        )
        self.db.refresh(withdrawal)
        self.assertEqual(withdrawal.created_platform, "web")
        self.assertEqual(withdrawal.last_modified_platform, "admin")

    def test_community_and_invite_writes_keep_client_origin(self):
        community_router.create_post(
            PostCreateIn(content="来自 Web 的社区内容"),
            self.user,
            self.db,
            "web",
        )
        post = self.db.query(Post).one()
        self.assertEqual(post.created_platform, "web")
        self.assertEqual(post.last_modified_platform, "web")

        invitee = User(
            phone="13900000003",
            username="被邀请用户",
            password="!",
            invited_by=self.user.id,
        )
        self.db.add(invitee)
        self.db.flush()
        relationship = create_invite_relationship(
            invitee,
            self.user.id,
            self.db,
            platform="ios",
        )
        self.db.commit()
        self.assertEqual(relationship.created_platform, "ios")
        self.assertEqual(relationship.last_modified_platform, "ios")


if __name__ == "__main__":
    unittest.main()
