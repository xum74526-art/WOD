import unittest
from decimal import Decimal
from unittest.mock import patch

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.db.base import Base
from app.models import User, Wallet  # noqa: F401
from app.models.invite import InviteCode, InviteRecord
from app.routers.auth import register
from app.schemas.user import RegisterIn


class RegistrationTruthTests(unittest.TestCase):
    def setUp(self):
        engine = create_engine(
            "sqlite://",
            connect_args={"check_same_thread": False},
            poolclass=StaticPool,
        )
        Base.metadata.create_all(engine)
        self.db = sessionmaker(bind=engine)()
        self.inviter = User(phone="13900000041", username="邀请人", password="!")
        self.db.add(self.inviter)
        self.db.flush()
        self.db.add(Wallet(user_id=self.inviter.id, balance=Decimal("0"), frozen=Decimal("0")))
        self.code = InviteCode(user_id=self.inviter.id, code="WODTEST01", invited_count=0)
        self.db.add(self.code)
        self.db.commit()

    def tearDown(self):
        self.db.close()

    def test_image_captcha_registration_does_not_claim_sms_binding_or_mint_invite_credit(self):
        with patch("app.routers.auth.verify_captcha", return_value=True):
            result = register(RegisterIn(
                username="未短信验证用户",
                phone="13900000042",
                password="test-password",
                invite_code=self.code.code,
                captcha_key="test-key",
                captcha_code="1234",
            ), self.db)

        created = self.db.query(User).filter(User.phone == "13900000042").one()
        wallet = self.db.query(Wallet).filter(Wallet.user_id == created.id).one()
        self.db.refresh(self.code)
        self.assertFalse(created.phone_bound)
        self.assertFalse(result["data"]["user"]["phone_bound"])
        self.assertIsNone(result["data"]["user"]["phone"])
        self.assertEqual(wallet.balance, Decimal("0"))
        self.assertEqual(self.code.invited_count, 0)
        relation = self.db.query(InviteRecord).filter(InviteRecord.invitee_id == created.id).one()
        self.assertEqual(relation.inviter_id, self.inviter.id)
        self.assertEqual(relation.status, "unverified")
        self.assertEqual(relation.reward_amount, 0)


if __name__ == "__main__":
    unittest.main()
