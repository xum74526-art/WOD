import unittest
from decimal import Decimal
from unittest.mock import patch

from fastapi import HTTPException
from sqlalchemy import create_engine
from sqlalchemy.orm import Query, sessionmaker
from sqlalchemy.pool import StaticPool

from app.db.base import Base
from app.models import AuthSession, User, Wallet  # noqa: F401
from app.models.invite import InviteCode, InviteRecord
from app.routers.auth import register
from app.schemas.user import RegisterIn
from app.utils.response import BizError


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

    @staticmethod
    def registration_data(phone: str, invite_code: str | None = "WODTEST01") -> RegisterIn:
        return RegisterIn(
            username="未短信验证用户",
            phone=phone,
            password="test-password",
            invite_code=invite_code,
            captcha_key="test-key",
            captcha_code="1234",
        )

    def assert_no_partial_registration(self, phone: str):
        self.assertIsNone(self.db.query(User).filter(User.phone == phone).first())
        self.assertEqual(self.db.query(User).count(), 1)
        self.assertEqual(self.db.query(Wallet).count(), 1)
        self.assertEqual(self.db.query(InviteCode).count(), 1)
        self.assertEqual(self.db.query(InviteRecord).count(), 0)
        self.assertEqual(self.db.query(AuthSession).count(), 0)

    def test_image_captcha_registration_does_not_claim_sms_binding_or_mint_invite_credit(self):
        with patch("app.routers.auth.verify_captcha", return_value=True):
            result = register(self.registration_data("13900000042"), self.db)

        created = self.db.query(User).filter(User.phone == "13900000042").one()
        wallet = self.db.query(Wallet).filter(Wallet.user_id == created.id).one()
        self.db.refresh(self.code)
        self.assertFalse(created.phone_bound)
        self.assertFalse(result["data"]["user"]["phone_bound"])
        self.assertIsNone(result["data"]["user"]["phone"])
        self.assertEqual(wallet.balance, Decimal("0"))
        self.assertEqual(wallet.frozen, Decimal("0"))
        self.assertEqual(wallet.promotional_balance, Decimal("0"))
        self.assertEqual(wallet.promotional_frozen, Decimal("0"))
        self.assertEqual(wallet.withdrawable_balance, Decimal("0"))
        self.assertEqual(wallet.withdraw_frozen, Decimal("0"))
        self.assertEqual(self.code.invited_count, 0)
        relation = self.db.query(InviteRecord).filter(InviteRecord.invitee_id == created.id).one()
        self.assertEqual(relation.inviter_id, self.inviter.id)
        self.assertEqual(relation.status, "unverified")
        self.assertEqual(relation.reward_amount, 0)
        self.assertEqual(self.db.query(InviteCode).filter(InviteCode.user_id == created.id).count(), 1)
        self.assertEqual(self.db.query(AuthSession).filter(AuthSession.user_id == created.id).count(), 1)

    def test_registration_normalizes_invite_code_before_lookup(self):
        phone = "13900000046"
        data = self.registration_data(phone, "  wodtest01  ")
        self.assertEqual(data.invite_code, "WODTEST01")

        with patch("app.routers.auth.verify_captcha", return_value=True):
            register(data, self.db)

        created = self.db.query(User).filter(User.phone == phone).one()
        relation = self.db.query(InviteRecord).filter(InviteRecord.invitee_id == created.id).one()
        self.assertEqual(relation.inviter_id, self.inviter.id)

    def test_invalid_invite_code_stops_registration_instead_of_being_ignored(self):
        phone = "13900000047"
        with (
            patch("app.routers.auth.verify_captcha", return_value=True),
            self.assertRaises(BizError) as caught,
        ):
            register(self.registration_data(phone, "missing-code"), self.db)

        self.assertEqual(caught.exception.msg, "邀请码无效，请检查后重试")
        self.assertEqual(caught.exception.status_code, 400)
        self.assertEqual(caught.exception.code, 1)
        self.assert_no_partial_registration(phone)

    def test_registration_rolls_back_user_wallet_and_relation_if_invite_code_fails(self):
        phone = "13900000043"
        with (
            patch("app.routers.auth.verify_captcha", return_value=True),
            patch("app.routers.auth._ensure_invite_code", side_effect=RuntimeError("invite code failed")),
            self.assertRaisesRegex(RuntimeError, "invite code failed"),
        ):
            register(self.registration_data(phone), self.db)

        self.assert_no_partial_registration(phone)

    def test_registration_rolls_back_everything_if_token_signing_fails(self):
        phone = "13900000044"
        with (
            patch("app.routers.auth.verify_captcha", return_value=True),
            patch("app.services.auth_session.create_access_token", side_effect=RuntimeError("signing failed")),
            self.assertRaisesRegex(RuntimeError, "signing failed"),
        ):
            register(self.registration_data(phone), self.db)

        self.assert_no_partial_registration(phone)

    def test_unique_phone_race_returns_the_existing_registration_error(self):
        phone = "13900000045"
        existing = User(phone=phone, username="已存在用户", password="!")
        self.db.add(existing)
        self.db.commit()
        real_first = Query.first
        missed_precheck = False

        def miss_first_user_lookup(query):
            nonlocal missed_precheck
            entity = query.column_descriptions[0].get("entity")
            if entity is User and not missed_precheck:
                missed_precheck = True
                return None
            return real_first(query)

        with (
            patch("app.routers.auth.verify_captcha", return_value=True),
            patch.object(Query, "first", miss_first_user_lookup),
            self.assertRaises(HTTPException) as caught,
        ):
            register(self.registration_data(phone), self.db)

        self.assertEqual(caught.exception.status_code, 400)
        self.assertEqual(caught.exception.detail, "该手机号已注册")
        self.assertEqual(self.db.query(User).filter(User.phone == phone).count(), 1)
        self.assertEqual(self.db.query(Wallet).filter(Wallet.user_id == existing.id).count(), 0)
        self.assertEqual(self.db.query(AuthSession).filter(AuthSession.user_id == existing.id).count(), 0)


if __name__ == "__main__":
    unittest.main()
