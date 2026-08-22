import base64
import hashlib
import json
import time
import unittest
from urllib.parse import parse_qs, urlparse

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.core.config import settings
from app.db.base import Base
from app.models import ExternalAuthBindTicket, ExternalAuthFlow, ExternalIdentity, User  # noqa: F401
from app.services import kai_auth
from app.routers import auth as auth_router
from app.utils.response import BizError


def _b64(value: bytes) -> str:
    return base64.urlsafe_b64encode(value).rstrip(b"=").decode("ascii")


class _Response:
    def __init__(self, payload):
        self.payload = payload

    def raise_for_status(self):
        return None

    def json(self):
        return self.payload


class _AsyncClient:
    jwks = {}

    def __init__(self, *args, **kwargs):
        pass

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        return None

    async def get(self, *args, **kwargs):
        return _Response(self.jwks)


class KaiAuthTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        engine = create_engine(
            "sqlite://",
            connect_args={"check_same_thread": False},
            poolclass=StaticPool,
        )
        Base.metadata.create_all(engine)
        self.db = sessionmaker(bind=engine)()
        self.original = {
            "KAI_AUTH_ISSUER": settings.KAI_AUTH_ISSUER,
            "KAI_AUTH_CLIENT_ID": settings.KAI_AUTH_CLIENT_ID,
            "KAI_AUTH_CLIENT_SECRET": settings.KAI_AUTH_CLIENT_SECRET,
            "KAI_AUTH_CALLBACK_URL": settings.KAI_AUTH_CALLBACK_URL,
            "KAI_AUTH_APP_RETURN_URL": settings.KAI_AUTH_APP_RETURN_URL,
            "KAI_AUTH_ALLOWED_RETURN_URLS": settings.KAI_AUTH_ALLOWED_RETURN_URLS,
        }

    def tearDown(self):
        self.db.close()
        for key, value in self.original.items():
            setattr(settings, key, value)

    def configure(self):
        settings.KAI_AUTH_ISSUER = "https://auth.kai.test"
        settings.KAI_AUTH_CLIENT_ID = "wod-test-client"
        settings.KAI_AUTH_CLIENT_SECRET = "test-secret"
        settings.KAI_AUTH_CALLBACK_URL = "https://api.wod.test/api/auth/kai/callback"
        settings.KAI_AUTH_APP_RETURN_URL = "wod://auth/kai"
        settings.KAI_AUTH_ALLOWED_RETURN_URLS = "https://web.wod.test/login"

    def test_unconfigured_provider_is_blocked(self):
        settings.KAI_AUTH_CLIENT_ID = ""
        settings.KAI_AUTH_CLIENT_SECRET = ""
        settings.KAI_AUTH_CALLBACK_URL = ""
        settings.KAI_AUTH_APP_RETURN_URL = ""
        self.assertFalse(kai_auth.public_config()["configured"])
        with self.assertRaisesRegex(BizError, "统一认证尚未配置"):
            kai_auth.create_authorization_flow(self.db, "login")

    def test_authorization_flow_uses_s256_and_server_side_state(self):
        self.configure()
        url = kai_auth.create_authorization_flow(self.db, "register")
        query = parse_qs(urlparse(url).query)
        self.assertEqual(query["code_challenge_method"], ["S256"])
        self.assertEqual(query["response_type"], ["code"])
        self.assertEqual(query["prompt"], ["create"])
        self.assertEqual(query["redirect_uri"], [settings.KAI_AUTH_CALLBACK_URL])
        flow = self.db.query(ExternalAuthFlow).one()
        expected = _b64(hashlib.sha256(flow.code_verifier.encode("ascii")).digest())
        self.assertEqual(query["code_challenge"], [expected])
        self.assertNotEqual(flow.state_hash, query["state"][0])

    def test_authorization_flow_accepts_only_an_allowlisted_client_return_url(self):
        self.configure()
        kai_auth.create_authorization_flow(self.db, "login", "https://web.wod.test/login")
        self.assertEqual(self.db.query(ExternalAuthFlow).one().return_url, "https://web.wod.test/login")
        with self.assertRaisesRegex(BizError, "返回地址无效"):
            kai_auth.create_authorization_flow(self.db, "login", "https://evil.example/login")

    def _user(self, phone: str = "13900000001") -> User:
        user = User(phone=phone, username="本地用户", password="!", supplier_status="none")
        self.db.add(user)
        self.db.commit()
        self.db.refresh(user)
        return user

    def test_unknown_identity_does_not_create_a_local_user(self):
        self.configure()
        claims = {
            "sub": "kai-user-001",
            "name": "Kai Tester",
            "email": "tester@example.com",
            "email_verified": True,
        }
        self.assertIsNone(kai_auth.find_bound_user(self.db, claims))
        self.assertEqual(self.db.query(User).count(), 0)
        self.assertEqual(self.db.query(ExternalIdentity).count(), 0)

    def test_verified_bind_ticket_explicitly_links_the_logged_in_user(self):
        self.configure()
        user = self._user()
        claims = {
            "sub": "kai-user-001",
            "name": "Kai Tester",
            "email": "tester@example.com",
            "email_verified": True,
        }
        ticket = kai_auth.issue_bind_ticket(
            self.db,
            user.id,
            claims,
            platform="android",
            client_id="android",
        )
        identity = kai_auth.bind_identity_with_ticket(self.db, ticket, user)
        self.assertEqual(identity.user_id, user.id)
        self.assertEqual(identity.subject, "kai-user-001")
        self.assertEqual(kai_auth.find_bound_user(self.db, claims).id, user.id)
        with self.assertRaisesRegex(BizError, "无效或已过期"):
            kai_auth.bind_identity_with_ticket(self.db, ticket, user)

    def test_bind_ticket_is_tied_to_initiating_user_and_uniqueness_is_enforced(self):
        self.configure()
        first = self._user("13900000001")
        second = self._user("13900000002")
        first_ticket = kai_auth.issue_bind_ticket(
            self.db,
            first.id,
            {"sub": "kai-user-001"},
            platform="web",
            client_id="web",
        )
        with self.assertRaisesRegex(BizError, "无效或已过期"):
            kai_auth.bind_identity_with_ticket(self.db, first_ticket, second)
        kai_auth.bind_identity_with_ticket(self.db, first_ticket, first)

        same_subject = kai_auth.issue_bind_ticket(
            self.db,
            second.id,
            {"sub": "kai-user-001"},
            platform="ios",
            client_id="ios",
        )
        with self.assertRaisesRegex(BizError, "已绑定其他账号"):
            kai_auth.bind_identity_with_ticket(self.db, same_subject, second)

        different_subject = kai_auth.issue_bind_ticket(
            self.db,
            first.id,
            {"sub": "kai-user-002"},
            platform="web",
            client_id="web",
        )
        with self.assertRaisesRegex(BizError, "当前账号已绑定其他"):
            kai_auth.bind_identity_with_ticket(self.db, different_subject, first)

    def test_handoff_ticket_is_single_use(self):
        self.configure()
        user = self._user()
        ticket = kai_auth.issue_handoff_ticket(
            self.db,
            user.id,
            platform="ios",
            client_id="ios",
        )
        consumed_user, platform, client_id = kai_auth.consume_handoff_ticket(self.db, ticket)
        self.assertEqual(consumed_user.id, user.id)
        self.assertEqual((platform, client_id), ("ios", "ios"))
        with self.assertRaisesRegex(BizError, "无效或已过期"):
            kai_auth.consume_handoff_ticket(self.db, ticket)

    def test_bind_flow_is_tied_to_authenticated_user_and_session_source(self):
        self.configure()
        user = self._user()
        kai_auth.create_authorization_flow(
            self.db,
            "bind",
            user_id=user.id,
            platform="android",
            client_id="android",
        )
        flow = self.db.query(ExternalAuthFlow).one()
        self.assertEqual(flow.intent, "bind")
        self.assertEqual(flow.user_id, user.id)
        self.assertEqual(flow.platform, "android")
        self.assertEqual(flow.client_id, "android")
        with self.assertRaisesRegex(BizError, "必须先登录"):
            kai_auth.create_authorization_flow(self.db, "bind")

    async def test_id_token_validates_eddsa_issuer_audience_and_nonce(self):
        self.configure()
        private_key = Ed25519PrivateKey.generate()
        public_raw = private_key.public_key().public_bytes(
            encoding=serialization.Encoding.Raw,
            format=serialization.PublicFormat.Raw,
        )
        header = {"alg": "EdDSA", "kid": "test-key", "typ": "JWT"}
        claims = {
            "iss": settings.KAI_AUTH_ISSUER,
            "sub": "verified-user",
            "aud": settings.KAI_AUTH_CLIENT_ID,
            "exp": int(time.time()) + 300,
            "iat": int(time.time()),
            "nonce": "expected-nonce",
        }
        head = _b64(json.dumps(header, separators=(",", ":")).encode())
        body = _b64(json.dumps(claims, separators=(",", ":")).encode())
        signature = _b64(private_key.sign(f"{head}.{body}".encode("ascii")))
        token = f"{head}.{body}.{signature}"
        _AsyncClient.jwks = {
            "keys": [{"kid": "test-key", "kty": "OKP", "crv": "Ed25519", "x": _b64(public_raw)}]
        }
        original_client = kai_auth.httpx.AsyncClient
        kai_auth.httpx.AsyncClient = _AsyncClient
        try:
            verified = await kai_auth.verify_id_token(token, "expected-nonce")
        finally:
            kai_auth.httpx.AsyncClient = original_client
        self.assertEqual(verified["sub"], "verified-user")

    async def test_callback_for_unknown_identity_returns_bind_required_without_creating_user(self):
        self.configure()
        authorization_url = kai_auth.create_authorization_flow(
            self.db,
            "login",
            client_id="android",
            platform="android",
        )
        state = parse_qs(urlparse(authorization_url).query)["state"][0]

        original_exchange = kai_auth.exchange_authorization_code
        original_verify = kai_auth.verify_id_token
        original_enrich = kai_auth.enrich_with_userinfo

        async def exchange(code, flow):
            return {"id_token": "verified-token"}

        async def verify(id_token, nonce):
            return {"sub": "not-bound-yet"}

        async def enrich(claims, access_token):
            return claims

        kai_auth.exchange_authorization_code = exchange
        kai_auth.verify_id_token = verify
        kai_auth.enrich_with_userinfo = enrich
        try:
            response = await auth_router.kai_callback(
                code="authorization-code",
                state=state,
                iss=settings.KAI_AUTH_ISSUER,
                error=None,
                db=self.db,
            )
        finally:
            kai_auth.exchange_authorization_code = original_exchange
            kai_auth.verify_id_token = original_verify
            kai_auth.enrich_with_userinfo = original_enrich
        location = response.headers["location"]
        self.assertEqual(parse_qs(urlparse(location).query)["kai_error"], ["identity_not_bound"])
        self.assertEqual(self.db.query(User).count(), 0)


if __name__ == "__main__":
    unittest.main()
