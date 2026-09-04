"""Deletion-only public limits: synthetic receipts, no real account or network."""

from datetime import timedelta
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.core.rate_limit import SlidingWindowRateLimiter
from app.db.base import Base
from app.db.session import get_db
from app.models import AccountDeletionRequest, User
from app.routers import account_deletion as router
from app.services import account_deletion as deletion
from app.services.auth_session import utcnow
from app.utils.response import BizError, error


def connection(peer="127.0.0.1", headers=()):
    return Request({"type": "http", "method": "POST", "path": "/", "headers": list(headers),
                    "client": (peer, 12345), "server": ("local", 8000), "scheme": "http"})


class AccountDeletionRateLimitTests(unittest.TestCase):
    def setUp(self):
        self.ticket_limiter = SlidingWindowRateLimiter(limit=2, window_seconds=60)
        self.invalid_limiter = SlidingWindowRateLimiter(limit=2, window_seconds=60)
        self.patches = [patch.object(router, "_ticket_limit", self.ticket_limiter),
                        patch.object(router, "_invalid_peer_limit", self.invalid_limiter)]
        for item in self.patches:
            item.start()
            self.addCleanup(item.stop)

    def test_valid_tickets_never_share_global_or_proxy_peer_bucket(self):
        request = connection()
        with patch.object(deletion, "_request", side_effect=lambda _db, ticket: SimpleNamespace(ticket_hash=ticket)):
            router._limit_public_request("verified-first", request, None)
            router._limit_public_request("verified-first", request, None)
            with self.assertRaises(HTTPException) as caught:
                router._limit_public_request("verified-first", request, None)
            self.assertEqual(caught.exception.status_code, 429)
            router._limit_public_request("verified-second", request, None)
        self.assertEqual(len(self.ticket_limiter._events), 2)
        self.assertEqual(len(self.invalid_limiter._events), 0)

    def test_invalid_request_flood_does_not_block_valid_receipt_on_same_peer(self):
        request = connection()
        with patch.object(deletion, "_request", side_effect=BizError("invalid", status_code=401)):
            for _ in range(2):
                with self.assertRaises(BizError):
                    router._limit_public_request("invented", request, None)
            with self.assertRaises(HTTPException) as caught:
                router._limit_public_request("another-invented", request, None)
            self.assertEqual(caught.exception.status_code, 429)
        with patch.object(deletion, "_request", return_value=SimpleNamespace(ticket_hash="valid-digest")):
            router._limit_public_request("valid", request, None)
        self.assertEqual(list(self.ticket_limiter._events), ["deletion:ticket:valid-digest"])

    def test_forwarded_headers_cannot_select_or_evade_invalid_peer_bucket(self):
        plain = connection("10.0.0.5")
        forged = connection("10.0.0.5", ((b"x-forwarded-for", b"203.0.113.66"),
                                           (b"forwarded", b"for=198.51.100.90")))
        self.assertEqual(router._invalid_peer_key(plain), router._invalid_peer_key(forged))
        with patch.object(deletion, "_request", side_effect=BizError("invalid", status_code=401)):
            for request in (plain, forged):
                with self.assertRaises(BizError):
                    router._limit_public_request("invented", request, None)
            with self.assertRaises(HTTPException):
                router._limit_public_request("invented", forged, None)

    def test_random_tickets_and_peers_cannot_allocate_unbounded_keys(self):
        with patch.object(deletion, "_request", side_effect=BizError("invalid", status_code=401)):
            for index in range(2000):
                try:
                    router._limit_public_request(f"invented-{index}", connection(f"2001:db8::{index:x}"), None)
                except (BizError, HTTPException):
                    pass
        self.assertEqual(len(self.ticket_limiter._events), 0)
        self.assertLessEqual(len(self.invalid_limiter._events), router._INVALID_PEER_BUCKETS)

    def test_expired_and_unknown_receipts_use_invalid_bucket_after_real_db_lookup(self):
        engine = create_engine("sqlite://")
        Base.metadata.create_all(engine)
        with sessionmaker(bind=engine)() as db:
            user = User(username="Synthetic", phone="13900008881", password="!")
            db.add(user)
            db.flush()
            expired = "expired-" + "a" * 40
            db.add(AccountDeletionRequest(user_id=user.id, ticket_hash=deletion._digest(expired), credential_digest="!",
                                          expires_at=utcnow() - timedelta(days=2), receipt_expires_at=utcnow() - timedelta(days=1)))
            db.commit()
            for ticket in (expired, "invented-" + "b" * 40):
                with self.assertRaises(BizError) as caught:
                    router._limit_public_request(ticket, connection(), db)
                self.assertEqual(caught.exception.status_code, 401)
        engine.dispose()
        self.assertEqual(len(self.ticket_limiter._events), 0)
        self.assertEqual(len(self.invalid_limiter._events), 1)

    def test_submit_and_status_share_only_their_own_valid_ticket_budget(self):
        engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
        Base.metadata.create_all(engine)
        with sessionmaker(bind=engine)() as db:
            user = User(username="Synthetic", phone="13900008882", password="!")
            db.add(user)
            db.flush()
            first, second = "a" * 43, "b" * 43
            for ticket in (first, second):
                db.add(AccountDeletionRequest(user_id=user.id, ticket_hash=deletion._digest(ticket), credential_digest="!",
                                              expires_at=utcnow() + timedelta(minutes=10), receipt_expires_at=utcnow() + timedelta(days=7)))
            db.commit()
            app = FastAPI()
            app.include_router(router.router)

            @app.exception_handler(BizError)
            async def on_error(_request, exc):
                return JSONResponse(status_code=exc.status_code, content=error(exc.msg))

            def provide_db():
                yield db

            app.dependency_overrides[get_db] = provide_db
            response = {"status": "verified", "blockers": [], "completed_at": None}
            with TestClient(app) as client, patch.object(deletion, "submit_deletion", return_value=response), \
                    patch.object(deletion, "deletion_status", return_value=response):
                self.assertEqual(client.post("/api/user/account-deletion/submit", json={"ticket": first, "confirm": True}).status_code, 200)
                self.assertEqual(client.post("/api/user/account-deletion/status", json={"ticket": first}).status_code, 200)
                limited = client.post("/api/user/account-deletion/status", json={"ticket": first})
                self.assertEqual(limited.status_code, 429)
                self.assertEqual(limited.headers["retry-after"], "60")
                self.assertEqual(client.post("/api/user/account-deletion/status", json={"ticket": second}).status_code, 200)
        engine.dispose()


if __name__ == "__main__":
    unittest.main()
