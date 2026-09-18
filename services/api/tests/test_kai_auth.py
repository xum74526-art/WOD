import base64
from concurrent.futures import ThreadPoolExecutor
import hashlib
import json
from pathlib import Path
from tempfile import TemporaryDirectory
from threading import Barrier, current_thread, local, main_thread
import time
import unittest
from unittest.mock import patch
from urllib.parse import parse_qs, urlparse

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import NullPool, StaticPool

from app.core.config import settings
from app.db.base import Base
from app.models import (  # noqa: F401
    AccountRecoveryToken,
    AuthSession,
    ExternalAuthBindTicket,
    ExternalAuthFlow,
    ExternalAuthTicket,
    ExternalIdentity,
    User,
)
from app.schemas.auth import KaiTicketIn
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

    def test_handoff_ticket_remains_retryable_if_session_creation_fails(self):
        self.configure()
        user = self._user()
        ticket = kai_auth.issue_handoff_ticket(
            self.db,
            user.id,
            platform="android",
            client_id="android",
        )

        with (
            patch(
                "app.services.auth_session.create_access_token",
                side_effect=RuntimeError("signing failed"),
            ),
            self.assertRaisesRegex(RuntimeError, "signing failed"),
        ):
            auth_router.kai_exchange(KaiTicketIn(ticket=ticket), self.db)

        row = self.db.query(ExternalAuthTicket).one()
        self.assertIsNone(row.consumed_at)
        self.assertEqual(self.db.query(AuthSession).count(), 0)

        result = auth_router.kai_exchange(KaiTicketIn(ticket=ticket), self.db)
        self.assertTrue(result["data"]["token"])
        self.db.refresh(row)
        self.assertIsNotNone(row.consumed_at)
        session = self.db.query(AuthSession).one()
        self.assertEqual(session.user_id, user.id)
        self.assertEqual(session.platform, "android")
        with self.assertRaisesRegex(BizError, "无效或已过期"):
            auth_router.kai_exchange(KaiTicketIn(ticket=ticket), self.db)

    def test_concurrent_handoff_exchange_creates_exactly_one_session(self):
        with TemporaryDirectory() as directory:
            database_path = Path(directory) / "kai-exchange.db"
            engine = create_engine(
                f"sqlite:///{database_path.as_posix()}",
                connect_args={"check_same_thread": False, "timeout": 10},
                poolclass=NullPool,
            )

            @event.listens_for(engine, "connect")
            def set_busy_timeout(connection, _record):
                cursor = connection.cursor()
                try:
                    cursor.execute("PRAGMA busy_timeout=10000")
                finally:
                    cursor.close()

            claim_barrier = Barrier(2)
            claim_seen = local()

            def synchronize_claims(_connection, _cursor, statement, _params, _context, _many):
                normalized = statement.strip().lower()
                if (
                    current_thread() is not main_thread()
                    and normalized.startswith("update external_auth_tickets")
                    and not getattr(claim_seen, "hit", False)
                ):
                    claim_seen.hit = True
                    claim_barrier.wait(timeout=10)

            try:
                Base.metadata.create_all(engine)
                with engine.connect() as connection:
                    connection.exec_driver_sql("PRAGMA journal_mode=WAL")
                Session = sessionmaker(bind=engine, expire_on_commit=False)
                with Session() as setup:
                    user = User(
                        phone="13900000077",
                        username="并发兑换用户",
                        password="!",
                    )
                    setup.add(user)
                    setup.commit()
                    user_id = user.id
                    ticket = kai_auth.issue_handoff_ticket(
                        setup,
                        user_id,
                        platform="ios",
                        client_id="ios",
                    )

                event.listen(engine, "before_cursor_execute", synchronize_claims)

                def redeem(_index):
                    with Session() as worker:
                        try:
                            result = auth_router.kai_exchange(
                                KaiTicketIn(ticket=ticket),
                                worker,
                            )
                            return "success", result["data"]["token"]
                        except BizError as exc:
                            return "rejected", exc.msg

                try:
                    with ThreadPoolExecutor(max_workers=2) as executor:
                        outcomes = list(executor.map(redeem, range(2)))
                finally:
                    event.remove(engine, "before_cursor_execute", synchronize_claims)

                self.assertEqual(
                    sorted(item[0] for item in outcomes),
                    ["rejected", "success"],
                )
                rejected = next(item[1] for item in outcomes if item[0] == "rejected")
                self.assertIn("无效或已过期", rejected)
                with Session() as check:
                    row = check.query(ExternalAuthTicket).one()
                    self.assertIsNotNone(row.consumed_at)
                    sessions = check.query(AuthSession).all()
                    self.assertEqual(len(sessions), 1)
                    self.assertEqual(sessions[0].user_id, user_id)
            finally:
                engine.dispose()

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

    def test_deletion_flow_is_user_bound_and_forces_fresh_login(self):
        self.configure()
        user = self._user()
        url = kai_auth.create_authorization_flow(
            self.db,
            "delete",
            user_id=user.id,
            platform="ios",
            client_id="ios",
        )
        query = parse_qs(urlparse(url).query)
        self.assertEqual(query["prompt"], ["login"])
        self.assertEqual(query["max_age"], ["0"])
        flow = self.db.query(ExternalAuthFlow).one()
        self.assertEqual((flow.intent, flow.user_id), ("delete", user.id))
        with self.assertRaisesRegex(BizError, "必须先登录"):
            kai_auth.create_authorization_flow(self.db, "delete")

    def test_deletion_reauth_rejects_a_different_bound_kai_subject(self):
        self.configure()
        initiating_user = self._user("13900000001")
        other_user = self._user("13900000002")
        identity = ExternalIdentity(
            user_id=other_user.id,
            provider="kai",
            issuer=settings.KAI_AUTH_ISSUER,
            subject="other-kai-user",
            display_name="Original name",
        )
        self.db.add(identity)
        self.db.commit()

        with self.assertRaisesRegex(BizError, "身份与当前账号不匹配"):
            kai_auth.find_bound_user(
                self.db,
                {"sub": "other-kai-user", "name": "Attacker-controlled update"},
                expected_user_id=initiating_user.id,
            )
        self.db.refresh(identity)
        self.assertEqual(identity.display_name, "Original name")
        self.assertEqual(self.db.query(AccountRecoveryToken).count(), 0)

    async def test_deletion_callback_returns_scoped_proof_in_fragment(self):
        self.configure()
        user = self._user()
        self.db.add(ExternalIdentity(
            user_id=user.id,
            provider="kai",
            issuer=settings.KAI_AUTH_ISSUER,
            subject="kai-delete-user",
        ))
        self.db.commit()
        url = kai_auth.create_authorization_flow(self.db, "delete", user_id=user.id)
        state = parse_qs(urlparse(url).query)["state"][0]

        async def exchange(_code, _flow):
            return {"id_token": "verified-token"}

        async def verify(_id_token, _nonce):
            return {"sub": "kai-delete-user"}

        async def enrich(claims, _access_token):
            return claims

        with (
            patch.object(kai_auth, "exchange_authorization_code", exchange),
            patch.object(kai_auth, "verify_id_token", verify),
            patch.object(kai_auth, "enrich_with_userinfo", enrich),
        ):
            response = await auth_router.kai_callback(
                code="authorization-code",
                state=state,
                iss=settings.KAI_AUTH_ISSUER,
                error=None,
                db=self.db,
            )
        parsed = urlparse(response.headers["location"])
        self.assertNotIn("kai_deletion_token", parse_qs(parsed.query))
        proof = parse_qs(parsed.fragment)["kai_deletion_token"][0]
        self.assertTrue(proof)
        self.assertNotIn(proof, repr(self.db.query(AccountRecoveryToken).all()))

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
