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
from app.models import ExternalAuthFlow, ExternalIdentity, User, Wallet  # noqa: F401
from app.schemas.user import UserOut
from app.services import kai_auth
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

    def test_identity_is_stable_personal_and_phone_unbound(self):
        self.configure()
        claims = {
            "sub": "kai-user-001",
            "name": "Kai Tester",
            "email": "tester@example.com",
            "email_verified": True,
        }
        user = kai_auth.find_or_create_user(self.db, claims)
        again = kai_auth.find_or_create_user(self.db, claims)
        self.assertEqual(user.id, again.id)
        self.assertEqual(user.role, "personal")
        self.assertEqual(user.supplier_status, "none")
        self.assertFalse(user.phone_bound)
        self.assertIsNone(UserOut.model_validate(user).phone)
        self.assertEqual(self.db.query(ExternalIdentity).count(), 1)
        self.assertEqual(self.db.query(Wallet).filter(Wallet.user_id == user.id).count(), 1)

    def test_handoff_ticket_is_single_use(self):
        self.configure()
        user = kai_auth.find_or_create_user(self.db, {"sub": "ticket-user", "name": "Ticket User"})
        ticket = kai_auth.issue_handoff_ticket(self.db, user.id)
        self.assertEqual(kai_auth.consume_handoff_ticket(self.db, ticket).id, user.id)
        with self.assertRaisesRegex(BizError, "无效或已过期"):
            kai_auth.consume_handoff_ticket(self.db, ticket)

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


if __name__ == "__main__":
    unittest.main()
