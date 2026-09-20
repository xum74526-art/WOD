import unittest

from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.core.config import settings
from app.core.deps import get_current_auth_context
from app.core.security import create_access_token, decode_access_token
from app.db.base import Base
from app.db.session import get_db
from app.models import AuthSession, User  # noqa: F401
from app.routers import auth as auth_router
from app.services.auth_session import create_authenticated_session, resolve_client
from app.utils.response import BizError


class AuthSessionTests(unittest.TestCase):
    def setUp(self):
        engine = create_engine(
            "sqlite://",
            connect_args={"check_same_thread": False},
            poolclass=StaticPool,
        )
        Base.metadata.create_all(engine)
        self.db = sessionmaker(bind=engine)()
        self.user = User(phone="13900000001", username="会话用户", password="!")
        self.db.add(self.user)
        self.db.commit()
        self.db.refresh(self.user)
        self.original_map = settings.AUTH_CLIENT_PLATFORM_MAP
        settings.AUTH_CLIENT_PLATFORM_MAP = "web-client=web,ios-client=ios,android-client=android,admin-client=admin"

    def tearDown(self):
        settings.AUTH_CLIENT_PLATFORM_MAP = self.original_map
        self.db.close()

    def test_registered_client_becomes_server_owned_session_attribution(self):
        platform, client_id = resolve_client("android-client", self.user)
        issued = create_authenticated_session(
            self.db,
            self.user,
            platform=platform,
            client_id=client_id,
            auth_method="password",
        )
        claims = decode_access_token(issued.token)
        self.assertIsNotNone(claims)
        context = get_current_auth_context(token=issued.token, db=self.db)
        self.assertEqual(context.user.id, self.user.id)
        self.assertEqual(context.platform, "android")
        self.assertEqual(context.client_id, "android-client")
        self.assertEqual(context.session_id, issued.session.id)

    def test_unknown_client_is_rejected_instead_of_becoming_a_platform(self):
        with self.assertRaisesRegex(BizError, "未注册"):
            resolve_client("x-platform-from-header", self.user)

    def test_legacy_token_cannot_self_assert_a_platform_without_server_session(self):
        token = create_access_token(self.user.id, platform="admin")
        context = get_current_auth_context(token=token, db=self.db)
        self.assertEqual(context.platform, "legacy")
        self.assertIsNone(context.session_id)

    def test_token_platform_must_match_persisted_session(self):
        issued = create_authenticated_session(
            self.db,
            self.user,
            platform="ios",
            client_id="ios-client",
            auth_method="password",
        )
        forged_mismatch = create_access_token(
            self.user.id,
            session_id=issued.session.id,
            platform="web",
        )
        with self.assertRaises(HTTPException) as caught:
            get_current_auth_context(token=forged_mismatch, db=self.db)
        self.assertEqual(caught.exception.status_code, 401)

    def test_admin_source_requires_admin_role(self):
        with self.assertRaisesRegex(BizError, "仅允许管理员"):
            resolve_client("admin-client", self.user)

    def test_logout_revokes_only_the_current_server_session(self):
        current = create_authenticated_session(
            self.db,
            self.user,
            platform="web",
            client_id="web-client",
            auth_method="password",
        )
        other = create_authenticated_session(
            self.db,
            self.user,
            platform="android",
            client_id="android-client",
            auth_method="password",
        )
        app = FastAPI()
        app.include_router(auth_router.router)

        def db_override():
            yield self.db

        app.dependency_overrides[get_db] = db_override
        with TestClient(app) as client:
            response = client.post(
                "/api/auth/logout",
                headers={"Authorization": f"Bearer {current.token}"},
            )
            anonymous = client.post("/api/auth/logout")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            response.json()["data"],
            {"logged_out": True, "session_revoked": True},
        )
        self.assertEqual(anonymous.status_code, 401)
        self.db.expire_all()
        self.assertIsNotNone(self.db.get(AuthSession, current.session.id).revoked_at)
        self.assertIsNone(self.db.get(AuthSession, other.session.id).revoked_at)
        with self.assertRaises(HTTPException) as caught:
            get_current_auth_context(token=current.token, db=self.db)
        self.assertEqual(caught.exception.status_code, 401)
        self.assertEqual(
            get_current_auth_context(token=other.token, db=self.db).session_id,
            other.session.id,
        )


if __name__ == "__main__":
    unittest.main()
