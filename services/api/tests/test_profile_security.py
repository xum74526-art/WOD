import asyncio
import io
import tempfile
import unittest
from datetime import timedelta
from pathlib import Path
from unittest.mock import patch

from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient
from PIL import Image
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool
from starlette.datastructures import Headers, UploadFile

from app.core.config import settings
from app.core.deps import get_current_user
from app.core.security import hash_password, verify_password
from app.db.base import Base
from app.models import AuthSession, ExternalIdentity, User  # noqa: F401
from app.routers import user as user_router
from app.schemas.user import ProfileUpdateIn
from app.utils.response import BizError
from app.services.account_credentials import (
    configure_initial_phone_login,
    internal_kai_phone,
    phone_login_status,
)
from app.services.auth_session import utcnow


def image_bytes(image_format: str = "PNG") -> bytes:
    stream = io.BytesIO()
    Image.new("RGB", (12, 12), color=(18, 175, 196)).save(stream, format=image_format)
    return stream.getvalue()


def upload_file(content: bytes, content_type: str = "image/png") -> UploadFile:
    return UploadFile(
        file=io.BytesIO(content),
        filename="chosen-image.png",
        headers=Headers({"content-type": content_type}),
    )


class ProfileSecurityTests(unittest.TestCase):
    def setUp(self):
        engine = create_engine(
            "sqlite://",
            connect_args={"check_same_thread": False},
            poolclass=StaticPool,
        )
        Base.metadata.create_all(engine)
        self.db = sessionmaker(bind=engine)()
        self.user = User(
            phone="13900000001",
            phone_bound=True,
            username="资料测试用户",
            password="!",
        )
        self.db.add(self.user)
        self.db.commit()
        self.db.refresh(self.user)

    def tearDown(self):
        self.db.close()

    def test_avatar_route_requires_current_user_dependency(self):
        route = next(route for route in user_router.router.routes if route.path == "/api/user/avatar")
        dependency_calls = {dependency.call for dependency in route.dependant.dependencies}
        self.assertIn(get_current_user, dependency_calls)

    def test_anonymous_avatar_upload_is_rejected(self):
        app = FastAPI()
        app.include_router(user_router.router)
        response = TestClient(app).post(
            "/api/user/avatar",
            files={"avatar": ("avatar.png", image_bytes(), "image/png")},
        )
        self.assertEqual(response.status_code, 401)

    def test_phone_cannot_change_without_verified_flow(self):
        with self.assertRaisesRegex(BizError, "验证码验证"):
            user_router.update_profile(
                ProfileUpdateIn(username="不应保存", phone="13900000002"),
                self.user,
                self.db,
            )
        self.db.refresh(self.user)
        self.assertEqual(self.user.phone, "13900000001")
        self.assertEqual(self.user.username, "资料测试用户")

    def test_same_phone_value_is_allowed(self):
        result = user_router.update_profile(
            ProfileUpdateIn(username="更新后的用户名", phone="13900000001"),
            self.user,
            self.db,
        )
        self.assertEqual(result["data"]["phone"], "13900000001")
        self.assertEqual(result["data"]["username"], "更新后的用户名")

    def test_profile_update_filters_and_normalizes_the_public_username(self):
        with self.assertRaisesRegex(BizError, "不适合公开发布"):
            user_router.update_profile(
                ProfileUpdateIn(username="出售毒品"),
                self.user,
                self.db,
            )
        self.db.refresh(self.user)
        self.assertEqual(self.user.username, "资料测试用户")

        result = user_router.update_profile(
            ProfileUpdateIn(username="  安全昵称  "),
            self.user,
            self.db,
        )
        self.assertEqual(result["data"]["username"], "安全昵称")

    def test_kai_only_account_cannot_fake_phone_binding_in_profile(self):
        kai_user = User(
            phone="__kai_pending_42",
            phone_bound=False,
            username="Kai 测试用户",
            password="!",
        )
        self.db.add(kai_user)
        self.db.commit()
        with self.assertRaisesRegex(BizError, "验证码验证"):
            user_router.update_profile(
                ProfileUpdateIn(phone="13900000009"), kai_user, self.db,
            )
        self.db.refresh(kai_user)
        self.assertFalse(kai_user.phone_bound)
        self.assertEqual(kai_user.phone, "__kai_pending_42")

    def test_kai_first_account_can_configure_unverified_phone_login_once(self):
        issuer = "https://auth.kai.test"
        subject = "phone-setup-user"
        kai_user = User(
            phone=internal_kai_phone(issuer, subject),
            phone_bound=False,
            username="Kai 登录设置用户",
            password=hash_password("unknown-random-placeholder"),
            password_set=False,
        )
        self.db.add(kai_user)
        self.db.flush()
        self.db.add(ExternalIdentity(
            user_id=kai_user.id,
            provider="kai",
            issuer=issuer,
            subject=subject,
        ))
        session = AuthSession(
            id="recent-kai-session",
            user_id=kai_user.id,
            platform="android",
            client_id="android",
            auth_method="kai_oidc",
            expires_at=utcnow() + timedelta(hours=1),
            created_at=utcnow(),
        )
        self.db.add(session)
        self.db.commit()

        before = phone_login_status(self.db, kai_user)
        self.assertFalse(before["configured"])
        self.assertTrue(before["can_configure"])
        updated = configure_initial_phone_login(
            self.db,
            kai_user,
            phone="13900000009",
            password="New-Password-42",
            current_session_id=session.id,
        )
        self.assertEqual(updated.phone, "13900000009")
        self.assertFalse(updated.phone_bound)
        self.assertTrue(updated.password_set)
        self.assertTrue(verify_password("New-Password-42", updated.password))
        status = phone_login_status(self.db, updated)
        self.assertTrue(status["configured"])
        self.assertFalse(status["phone_verified"])
        self.assertEqual(status["phone_masked"], "139****0009")
        with self.assertRaisesRegex(BizError, "已设置"):
            configure_initial_phone_login(
                self.db,
                updated,
                phone="13900000008",
                password="Other-Password-42",
                current_session_id=session.id,
            )

    def test_kai_phone_setup_requires_a_recent_kai_session_and_never_merges(self):
        previous_age = settings.KAI_AUTH_REAUTH_MAX_AGE_SECONDS
        settings.KAI_AUTH_REAUTH_MAX_AGE_SECONDS = 600
        try:
            issuer = "https://auth.kai.test"
            kai_user = User(
                phone=internal_kai_phone(issuer, "stale-user"),
                phone_bound=False,
                username="Kai 过期会话用户",
                password=hash_password("unknown-random-placeholder"),
                password_set=False,
            )
            self.db.add(kai_user)
            self.db.flush()
            self.db.add(ExternalIdentity(
                user_id=kai_user.id,
                provider="kai",
                issuer=issuer,
                subject="stale-user",
            ))
            stale = AuthSession(
                id="stale-kai-session",
                user_id=kai_user.id,
                platform="ios",
                client_id="ios",
                auth_method="kai_oidc",
                expires_at=utcnow() + timedelta(hours=1),
                created_at=utcnow() - timedelta(minutes=11),
            )
            self.db.add(stale)
            self.db.commit()
            with self.assertRaisesRegex(BizError, "最近一次 KAI 登录"):
                configure_initial_phone_login(
                    self.db,
                    kai_user,
                    phone=self.user.phone,
                    password="New-Password-42",
                    current_session_id=stale.id,
                )
            self.db.refresh(kai_user)
            self.assertTrue(kai_user.phone.startswith("__kai_"))
        finally:
            settings.KAI_AUTH_REAUTH_MAX_AGE_SECONDS = previous_age

    def test_arbitrary_avatar_url_cannot_be_saved_through_profile(self):
        with self.assertRaisesRegex(BizError, "头像上传"):
            user_router.update_profile(
                ProfileUpdateIn(avatar="file:///temporary/chosen.jpg"),
                self.user,
                self.db,
            )
        self.assertIsNone(self.user.avatar)

    def test_valid_png_is_persisted_by_user_id_and_returned_as_api_relative_url(self):
        with tempfile.TemporaryDirectory() as temp_dir, patch.object(
            user_router, "AVATAR_DIR", Path(temp_dir),
        ):
            result = asyncio.run(user_router.upload_avatar(
                upload_file(image_bytes()), self.user, self.db,
            ))
            relative_url = result["data"]["avatar"]
            self.assertTrue(relative_url.startswith(f"/user/avatars/avatar_{self.user.id}.png?v="))
            self.assertTrue((Path(temp_dir) / f"avatar_{self.user.id}.png").is_file())
            self.db.refresh(self.user)
            self.assertEqual(self.user.avatar, relative_url)

            response = user_router.public_avatar(f"avatar_{self.user.id}.png", db=self.db)
            self.assertEqual(response.media_type, "image/png")
            self.assertEqual(response.headers["x-content-type-options"], "nosniff")

    def test_spoofed_or_damaged_image_is_rejected(self):
        forged = b"\x89PNG\r\n\x1a\n" + b"not-an-image"
        with tempfile.TemporaryDirectory() as temp_dir, patch.object(
            user_router, "AVATAR_DIR", Path(temp_dir),
        ):
            with self.assertRaises(BizError):
                asyncio.run(user_router.upload_avatar(
                    upload_file(forged), self.user, self.db,
                ))
            self.assertEqual(list(Path(temp_dir).iterdir()), [])

    def test_avatar_size_limit_is_enforced_before_decoding(self):
        oversized = b"\x89PNG\r\n\x1a\n" + b"0" * (2 * 1024 * 1024)
        with self.assertRaisesRegex(BizError, "2MB"):
            asyncio.run(user_router.upload_avatar(
                upload_file(oversized), self.user, self.db,
            ))

    def test_public_route_cannot_escape_into_identity_uploads(self):
        with self.assertRaises(HTTPException) as raised:
            user_router.public_avatar("../id_cards/id_front_1.jpg")
        self.assertEqual(raised.exception.status_code, 404)


if __name__ == "__main__":
    unittest.main()
