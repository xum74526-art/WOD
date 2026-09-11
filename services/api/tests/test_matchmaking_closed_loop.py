import json
import tempfile
import threading
import unittest
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from pathlib import Path
from unittest.mock import patch

from cryptography.fernet import Fernet
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.exc import OperationalError
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.core.config import settings
from app.core.deps import get_current_user
from app.db.base import Base
from app.db.session import get_db
from app.models import (
    BuyRequest,
    BuyRequestCredential,
    BuyRequestDeal,
    BuyRequestEvent,
    BuyRequestQuote,
    BuyRequestQuoteRevision,
    Ledger,
    Order,
    PaymentOrder,
    RewardAccrual,
    Supplier,
    User,
    Wallet,
)
from app.routers import buy_request as buy_request_router
from app.services import buy_request_matchmaking as matchmaking
from app.utils.response import BizError, error
from init_db import _migrate_buy_request_quote_revisions


class MatchmakingClosedLoopTests(unittest.TestCase):
    def setUp(self):
        self.original = {
            name: getattr(settings, name)
            for name in (
                "DIRECT_TRADE_ENABLED",
                "MATCHMAKING_ENABLED",
                "MATCHMAKING_CREDENTIAL_ESCROW_ENABLED",
                "SECRET_KEY",
                "SENSITIVE_DATA_KEY",
            )
        }
        settings.DIRECT_TRADE_ENABLED = False
        settings.MATCHMAKING_ENABLED = True
        settings.MATCHMAKING_CREDENTIAL_ESCROW_ENABLED = True
        settings.SECRET_KEY = "unit-test-matchmaking-secret-key"
        settings.SENSITIVE_DATA_KEY = Fernet.generate_key().decode("ascii")
        self.engine = create_engine(
            "sqlite://",
            connect_args={"check_same_thread": False},
            poolclass=StaticPool,
        )
        Base.metadata.create_all(self.engine)
        self.db = sessionmaker(bind=self.engine)()

        self.buyer = User(username="采购方", phone="13910000001", password="!", role="personal")
        self.supplier_user = User(
            username="供应方一", phone="13910000002", password="!", role="supplier",
            supplier_status="approved",
        )
        self.other_supplier_user = User(
            username="供应方二", phone="13910000003", password="!", role="supplier",
            supplier_status="approved",
        )
        self.admin = User(username="管理员", phone="13910000004", password="!", role="admin")
        self.stranger = User(username="其他买家", phone="13910000005", password="!", role="personal")
        self.db.add_all([
            self.buyer, self.supplier_user, self.other_supplier_user, self.admin, self.stranger,
        ])
        self.db.flush()
        self.supplier = Supplier(
            user_id=self.supplier_user.id,
            company_name="甲方算力",
            contact="甲联系人",
            phone="13910000002",
            status="approved",
            rating=4.8,
        )
        self.other_supplier = Supplier(
            user_id=self.other_supplier_user.id,
            company_name="乙方算力",
            contact="乙联系人",
            phone="13910000003",
            status="approved",
            rating=4.7,
        )
        self.db.add_all([self.supplier, self.other_supplier])
        self.db.commit()

        self.current_user = self.buyer
        app = FastAPI()

        @app.exception_handler(BizError)
        async def handle_biz_error(request: Request, exc: BizError):
            del request
            return JSONResponse(status_code=exc.status_code, content=error(exc.msg, exc.code))

        def db_override():
            yield self.db

        app.include_router(buy_request_router.router)
        app.include_router(buy_request_router.admin_router)
        app.dependency_overrides[get_db] = db_override
        app.dependency_overrides[get_current_user] = lambda: self.current_user
        self.client = TestClient(app)

    def tearDown(self):
        for name, value in self.original.items():
            setattr(settings, name, value)
        self.client.close()
        self.db.close()
        self.engine.dispose()

    def _request(self) -> BuyRequest:
        row = BuyRequest(
            user_id=self.buyer.id,
            request_type="online",
            gpu_model="H200 141GB",
            quantity=1,
            gpu_hours=24,
            currency="CNY",
            requirements={
                "memory": "141GB",
                "phone": "13910000001",
                "nested": {"contact": "不应向商家公开", "note": "请联系不应向商家公开"},
            },
            contact="不应向商家公开",
            phone="13910000001",
            status="published",
            expires_at=datetime.now(timezone.utc).replace(tzinfo=None) + timedelta(days=1),
        )
        self.db.add(row)
        self.db.commit()
        return row

    def _set_user(self, user: User) -> None:
        self.current_user = user

    def _post(self, path: str, payload=None, expected: int = 200):
        response = self.client.post(path, json=payload) if payload is not None else self.client.post(path)
        self.assertEqual(response.status_code, expected, response.text)
        return response.json().get("data")

    def _get(self, path: str, expected: int = 200):
        response = self.client.get(path)
        self.assertEqual(response.status_code, expected, response.text)
        return response.json().get("data")

    def _quote(self, request: BuyRequest, supplier_user: User, total: float = 100):
        self._set_user(supplier_user)
        return self._post(f"/api/buy-requests/{request.id}/quotes", {
            "unit_price": 4.166667,
            "total_price": total,
            "currency": "CNY",
            "message": "首版方案",
            "expires_in_hours": 24,
        })

    def _select_and_confirm(self, request: BuyRequest, quote_id: int):
        self._set_user(self.buyer)
        selected = self._post(f"/api/buy-requests/{request.id}/quotes/{quote_id}/select")
        deal = selected["deal"]
        self._set_user(self.supplier_user)
        confirmed = self._post(
            f"/api/buy-requests/{request.id}/deals/{deal['id']}/supplier-confirm"
        )
        self.assertEqual(confirmed["status"], "platform_review")
        self._set_user(self.admin)
        approved = self._post(
            f"/api/admin/buy-requests/{request.id}/deals/{deal['id']}/approve"
        )
        self.assertEqual(approved["status"], "credential_pending")
        return deal["id"]

    def test_supplier_detail_is_anonymous_and_contains_only_own_quotes(self):
        request = self._request()
        first = self._quote(request, self.supplier_user, 100)
        second = self._quote(request, self.other_supplier_user, 110)
        first_quote = self.db.get(BuyRequestQuote, first["id"])
        first_quote.message = f"方案说明，联系{self.supplier.contact} {self.supplier.phone}"
        self.db.query(BuyRequestQuoteRevision).filter(
            BuyRequestQuoteRevision.quote_id == first["id"],
        ).one().message = first_quote.message
        self.db.commit()

        self._set_user(self.supplier_user)
        detail = self._get(f"/api/buy-requests/{request.id}")
        request_data = detail["request"]
        for key in ("user_id", "buyer_name", "contact", "phone"):
            self.assertIsNone(request_data[key], key)
        self.assertEqual([row["id"] for row in detail["quotes"]], [first["id"]])
        encoded = json.dumps(detail, ensure_ascii=False)
        self.assertNotIn(self.buyer.username, encoded)
        self.assertNotIn(self.buyer.phone, encoded)
        self.assertNotIn("不应向商家公开", encoded)
        self.assertNotIn("13910000001", encoded)
        self.assertNotIn(str(second["id"]), json.dumps([row["id"] for row in detail["quotes"]]))

        self._set_user(self.buyer)
        buyer_detail = self._get(f"/api/buy-requests/{request.id}")
        self.assertEqual(len(buyer_detail["quotes"]), 2)
        self.assertEqual(
            {row["supplier_name"] for row in buyer_detail["quotes"]},
            {"甲方算力", "乙方算力"},
        )
        self.assertNotIn("甲联系人", json.dumps(buyer_detail, ensure_ascii=False))
        self.assertNotIn(self.supplier.phone, json.dumps(buyer_detail, ensure_ascii=False))

    def test_counteroffers_alternate_preserve_history_and_withdraw_is_idempotent(self):
        request = self._request()
        quote = self._quote(request, self.supplier_user, 100)
        self.assertEqual(quote["revision_count"], 1)
        self.assertEqual(quote["latest_revision"]["actor_role"], "supplier")

        self._set_user(self.buyer)
        counter = self._post(
            f"/api/buy-requests/{request.id}/quotes/{quote['id']}/counter",
            {"total_price": 90, "currency": "CNY", "message": "买家还价", "expires_in_hours": 12},
        )
        self.assertEqual(counter["total_price"], 90)
        self.assertEqual(counter["revision_count"], 2)
        self.assertEqual(counter["latest_revision"]["actor_role"], "buyer")
        self._post(
            f"/api/buy-requests/{request.id}/quotes/{quote['id']}/counter",
            {"total_price": 85, "currency": "CNY", "expires_in_hours": 12},
            expected=409,
        )

        self._set_user(self.supplier_user)
        revised = self._post(
            f"/api/buy-requests/{request.id}/quotes/{quote['id']}/counter",
            {"total_price": 95, "currency": "CNY", "message": "商家新方案", "expires_in_hours": 12},
        )
        self.assertEqual(revised["revision_count"], 3)
        self.assertEqual([row["revision_no"] for row in revised["revisions"]], [1, 2, 3])

        withdrawn = self._post(
            f"/api/buy-requests/{request.id}/quotes/{quote['id']}/withdraw"
        )
        self.assertEqual(withdrawn["status"], "withdrawn")
        retry = self._post(f"/api/buy-requests/{request.id}/quotes/{quote['id']}/withdraw")
        self.assertEqual(retry["status"], "withdrawn")

    def test_full_lifecycle_is_idempotent_encrypted_and_non_financial(self):
        request = self._request()
        quote = self._quote(request, self.supplier_user, 100)
        self._quote(request, self.other_supplier_user, 110)
        financial_before = (
            self.db.query(Order).count(),
            self.db.query(Wallet).count(),
            self.db.query(Ledger).count(),
            self.db.query(PaymentOrder).count(),
            self.db.query(RewardAccrual).count(),
        )

        self._set_user(self.buyer)
        selection = self._post(f"/api/buy-requests/{request.id}/quotes/{quote['id']}/select")
        deal = selection["deal"]
        self.assertEqual(deal["status"], "buyer_selected")
        retry = self._post(f"/api/buy-requests/{request.id}/quotes/{quote['id']}/select")
        self.assertEqual(retry["deal"]["id"], deal["id"])
        self.assertEqual(self.db.query(BuyRequestDeal).count(), 1)

        self._set_user(self.supplier_user)
        self._post(
            f"/api/buy-requests/{request.id}/deals/{deal['id']}/supplier-confirm",
            {"expected_version": 999},
            expected=409,
        )
        confirmed = self._post(
            f"/api/buy-requests/{request.id}/deals/{deal['id']}/supplier-confirm"
        )
        self.assertEqual(confirmed["status"], "platform_review")
        confirmed_retry = self._post(
            f"/api/buy-requests/{request.id}/deals/{deal['id']}/supplier-confirm"
        )
        self.assertEqual(confirmed_retry["version"], confirmed["version"])

        self._set_user(self.admin)
        approved = self._post(
            f"/api/admin/buy-requests/{request.id}/deals/{deal['id']}/approve"
        )
        self.assertEqual(approved["status"], "credential_pending")
        self.assertTrue(approved["can_admin_reject"] is False)

        self._set_user(self.buyer)
        self._get(
            f"/api/buy-requests/{request.id}/deals/{deal['id']}/credential",
            expected=403,
        )

        credential_payload = {
            "host": "203.0.113.20",
            "port": 2222,
            "username": "ubuntu",
            "auth_type": "password",
            "secret": "NotStoredInPlaintext!",
            "note": "24 小时测试资源",
        }
        self._set_user(self.supplier_user)
        submitted = self._post(
            f"/api/buy-requests/{request.id}/deals/{deal['id']}/credential",
            credential_payload,
        )
        self.assertEqual(submitted["status"], "credential_submitted")
        stored = self.db.query(BuyRequestCredential).filter(
            BuyRequestCredential.deal_id == deal["id"],
        ).one()
        self.assertTrue(stored.protected_payload.startswith("enc:v1:"))
        self.assertNotIn(credential_payload["host"], stored.protected_payload)
        self.assertNotIn(credential_payload["secret"], stored.protected_payload)
        event_dump = json.dumps([
            row.event_data for row in self.db.query(BuyRequestEvent).all()
        ], ensure_ascii=False)
        self.assertNotIn(credential_payload["host"], event_dump)
        self.assertNotIn(credential_payload["secret"], event_dump)

        self._set_user(self.admin)
        admin_detail = self._get(f"/api/admin/buy-requests/{request.id}")
        self.assertEqual(admin_detail["deal"]["credential_status"], "submitted")
        self.assertNotIn(credential_payload["secret"], json.dumps(admin_detail, ensure_ascii=False))
        inspected = self._get(
            f"/api/admin/buy-requests/{request.id}/deals/{deal['id']}/credential"
        )
        self.assertEqual(inspected["secret"], credential_payload["secret"])
        released = self._post(
            f"/api/admin/buy-requests/{request.id}/deals/{deal['id']}/credential/release"
        )
        self.assertEqual(released["status"], "credential_released")
        release_retry = self._post(
            f"/api/admin/buy-requests/{request.id}/deals/{deal['id']}/credential/release"
        )
        self.assertEqual(release_retry["version"], released["version"])

        self._set_user(self.buyer)
        revealed = self._get(f"/api/buy-requests/{request.id}/deals/{deal['id']}/credential")
        self.assertEqual(revealed["secret"], credential_payload["secret"])
        completed = self._post(
            f"/api/buy-requests/{request.id}/deals/{deal['id']}/confirm-delivery"
        )
        self.assertEqual(completed["status"], "completed")
        completed_retry = self._post(
            f"/api/buy-requests/{request.id}/deals/{deal['id']}/confirm-delivery"
        )
        self.assertEqual(completed_retry["version"], completed["version"])
        completed_detail = self._get(f"/api/buy-requests/{request.id}")
        self.assertEqual(completed_detail["request"]["quote_count"], 2)
        self.assertEqual(len(completed_detail["quotes"]), 2)

        self.assertEqual(financial_before, (
            self.db.query(Order).count(),
            self.db.query(Wallet).count(),
            self.db.query(Ledger).count(),
            self.db.query(PaymentOrder).count(),
            self.db.query(RewardAccrual).count(),
        ))

    def test_rejection_dispute_resubmission_and_permissions(self):
        request = self._request()
        quote = self._quote(request, self.supplier_user, 100)
        deal_id = self._select_and_confirm(request, quote["id"])

        self._set_user(self.other_supplier_user)
        self._post(
            f"/api/buy-requests/{request.id}/deals/{deal_id}/supplier-confirm",
            expected=404,
        )

        first = {
            "host": "203.0.113.21", "port": 22, "username": "root",
            "auth_type": "private_key", "secret": "FIRST-PRIVATE-KEY",
        }
        self._set_user(self.supplier_user)
        self._post(f"/api/buy-requests/{request.id}/deals/{deal_id}/credential", first)
        self._set_user(self.admin)
        rejected = self._post(
            f"/api/admin/buy-requests/{request.id}/deals/{deal_id}/credential/reject",
            {"reason": "端口不可达"},
        )
        self.assertEqual(rejected["status"], "credential_rejected")

        second = {**first, "host": "203.0.113.22", "secret": "SECOND-PRIVATE-KEY"}
        self._set_user(self.supplier_user)
        self._post(f"/api/buy-requests/{request.id}/deals/{deal_id}/credential", second)
        row = self.db.query(BuyRequestCredential).filter(BuyRequestCredential.deal_id == deal_id).one()
        self.assertEqual(row.credential_version, 2)
        self._set_user(self.admin)
        self._post(f"/api/admin/buy-requests/{request.id}/deals/{deal_id}/credential/release")

        self._set_user(self.stranger)
        self._get(f"/api/buy-requests/{request.id}/deals/{deal_id}/credential", expected=404)
        self._set_user(self.buyer)
        disputed = self._post(
            f"/api/buy-requests/{request.id}/deals/{deal_id}/report-delivery",
            {"reason": "SSH 握手失败"},
        )
        self.assertEqual(disputed["status"], "delivery_disputed")

        self._set_user(self.admin)
        rejected_again = self._post(
            f"/api/admin/buy-requests/{request.id}/deals/{deal_id}/credential/reject",
            {"reason": "要求商家重新交付"},
        )
        self.assertEqual(rejected_again["status"], "credential_rejected")
        self._set_user(self.supplier_user)
        third = {**second, "host": "203.0.113.23", "secret": "THIRD-PRIVATE-KEY"}
        self._post(f"/api/buy-requests/{request.id}/deals/{deal_id}/credential", third)
        row = self.db.query(BuyRequestCredential).filter(BuyRequestCredential.deal_id == deal_id).one()
        self.assertEqual(row.credential_version, 3)

    def test_expired_request_cannot_be_selected_and_escrow_switch_is_enforced(self):
        request = self._request()
        quote = self._quote(request, self.supplier_user, 100)
        request.expires_at = datetime.now(timezone.utc).replace(tzinfo=None) - timedelta(seconds=1)
        self.db.commit()
        self._set_user(self.buyer)
        self._post(
            f"/api/buy-requests/{request.id}/quotes/{quote['id']}/select",
            expected=409,
        )

        request.expires_at = datetime.now(timezone.utc).replace(tzinfo=None) + timedelta(days=1)
        request.status = "published"
        self.db.query(BuyRequestQuote).filter(BuyRequestQuote.id == quote["id"]).one().status = "active"
        self.db.commit()
        deal_id = self._select_and_confirm(request, quote["id"])
        settings.MATCHMAKING_CREDENTIAL_ESCROW_ENABLED = False
        self._set_user(self.supplier_user)
        self._post(
            f"/api/buy-requests/{request.id}/deals/{deal_id}/credential",
            {
                "host": "203.0.113.24", "port": 22, "username": "root",
                "auth_type": "password", "secret": "closed",
            },
            expected=409,
        )

    def test_credential_submission_fails_closed_when_sensitive_config_is_unsafe(self):
        request = self._request()
        quote = self._quote(request, self.supplier_user, 100)
        deal_id = self._select_and_confirm(request, quote["id"])
        self._set_user(self.supplier_user)

        with patch(
            "app.services.trade_mode.sensitive_security_errors",
            return_value=("default_secret_key", "missing_sensitive_data_key"),
        ):
            self._post(
                f"/api/buy-requests/{request.id}/deals/{deal_id}/credential",
                {
                    "host": "203.0.113.24",
                    "port": 22,
                    "username": "root",
                    "auth_type": "password",
                    "secret": "must-not-be-stored",
                },
                expected=409,
            )

        deal = self.db.get(BuyRequestDeal, deal_id)
        self.assertEqual(deal.status, "credential_pending")
        self.assertEqual(
            self.db.query(BuyRequestCredential).filter(
                BuyRequestCredential.deal_id == deal_id,
            ).count(),
            0,
        )

    @staticmethod
    def _seed_concurrent_negotiation_database(database: Path):
        engine = create_engine(
            f"sqlite:///{database}",
            connect_args={"check_same_thread": False, "timeout": 10},
        )
        Base.metadata.create_all(engine)
        Session = sessionmaker(bind=engine, expire_on_commit=False)
        seed = Session()
        buyer = User(username="并发议价买家", phone="13922000001", password="!")
        supplier_user = User(
            username="并发议价商家",
            phone="13922000002",
            password="!",
            role="supplier",
            supplier_status="approved",
        )
        seed.add_all([buyer, supplier_user])
        seed.flush()
        supplier = Supplier(
            user_id=supplier_user.id,
            company_name="并发议价商家",
            contact="议价联系人",
            phone=supplier_user.phone,
            status="approved",
        )
        seed.add(supplier)
        seed.flush()
        request = BuyRequest(
            user_id=buyer.id,
            request_type="online",
            gpu_model="H100 80GB",
            quantity=1,
            gpu_hours=24,
            currency="CNY",
            requirements={},
            status="quoting",
            expires_at=datetime.now(timezone.utc).replace(tzinfo=None) + timedelta(days=1),
        )
        seed.add(request)
        seed.flush()
        quote = BuyRequestQuote(
            buy_request_id=request.id,
            supplier_id=supplier.id,
            unit_price=Decimal("4.166667"),
            total_price=Decimal("100.00"),
            currency="CNY",
            message="初始方案",
            status="active",
            expires_at=datetime.now(timezone.utc).replace(tzinfo=None) + timedelta(days=1),
        )
        seed.add(quote)
        seed.flush()
        seed.add(BuyRequestQuoteRevision(
            quote_id=quote.id,
            buy_request_id=request.id,
            supplier_id=supplier.id,
            revision_number=1,
            proposer_role="supplier",
            proposer_user_id=supplier_user.id,
            unit_price=quote.unit_price,
            total_price=quote.total_price,
            currency=quote.currency,
            message=quote.message,
            expires_at=quote.expires_at,
            status="active",
        ))
        seed.commit()
        ids = {
            "request": request.id,
            "quote": quote.id,
            "buyer": buyer.id,
            "supplier_user": supplier_user.id,
        }
        seed.close()
        return engine, Session, ids

    def test_counter_and_selection_never_commit_different_quote_revisions(self):
        with tempfile.TemporaryDirectory() as tempdir:
            engine, Session, ids = self._seed_concurrent_negotiation_database(
                Path(tempdir) / "counter-select.db"
            )
            barrier = threading.Barrier(2)

            def counter() -> str:
                db = Session()
                try:
                    buyer = db.get(User, ids["buyer"])
                    barrier.wait(timeout=5)
                    buy_request_router.counter_quote(
                        ids["request"],
                        ids["quote"],
                        buy_request_router.QuoteRevisionIn(
                            unit_price=3.75,
                            total_price=90,
                            currency="CNY",
                            message="并发还价",
                            expires_in_hours=24,
                        ),
                        buyer,
                        db,
                    )
                    return "countered"
                except BizError:
                    db.rollback()
                    return "conflict"
                finally:
                    db.close()

            def select() -> str:
                db = Session()
                try:
                    buyer = db.get(User, ids["buyer"])
                    barrier.wait(timeout=5)
                    buy_request_router.select_quote(
                        ids["request"], ids["quote"], buyer, db
                    )
                    return "selected"
                except BizError:
                    db.rollback()
                    return "conflict"
                finally:
                    db.close()

            with ThreadPoolExecutor(max_workers=2) as pool:
                counter_future = pool.submit(counter)
                select_future = pool.submit(select)
                results = [counter_future.result(), select_future.result()]

            check = Session()
            try:
                deal = check.query(BuyRequestDeal).one()
                selected_revision = check.get(
                    BuyRequestQuoteRevision, deal.selected_revision_id
                )
                latest_revision = matchmaking.latest_revision(check, ids["quote"])
                quote = check.get(BuyRequestQuote, ids["quote"])
                self.assertIn("selected", results)
                self.assertEqual(selected_revision.id, latest_revision.id)
                self.assertEqual(selected_revision.status, "selected")
                self.assertEqual(quote.total_price, selected_revision.total_price)
                self.assertEqual(quote.status, "coordination_requested")
            finally:
                check.close()
                engine.dispose()

    def test_withdraw_and_selection_cannot_both_succeed(self):
        with tempfile.TemporaryDirectory() as tempdir:
            engine, Session, ids = self._seed_concurrent_negotiation_database(
                Path(tempdir) / "withdraw-select.db"
            )
            barrier = threading.Barrier(2)

            def withdraw() -> str:
                db = Session()
                try:
                    supplier_user = db.get(User, ids["supplier_user"])
                    barrier.wait(timeout=5)
                    buy_request_router.withdraw_quote(
                        ids["request"], ids["quote"], supplier_user, db
                    )
                    return "withdrawn"
                except BizError:
                    db.rollback()
                    return "conflict"
                finally:
                    db.close()

            def select() -> str:
                db = Session()
                try:
                    buyer = db.get(User, ids["buyer"])
                    barrier.wait(timeout=5)
                    buy_request_router.select_quote(
                        ids["request"], ids["quote"], buyer, db
                    )
                    return "selected"
                except BizError:
                    db.rollback()
                    return "conflict"
                finally:
                    db.close()

            with ThreadPoolExecutor(max_workers=2) as pool:
                withdraw_future = pool.submit(withdraw)
                select_future = pool.submit(select)
                results = [withdraw_future.result(), select_future.result()]

            self.assertEqual(sum(
                result in ("selected", "withdrawn") for result in results
            ), 1)
            check = Session()
            try:
                quote = check.get(BuyRequestQuote, ids["quote"])
                revision = matchmaking.latest_revision(check, ids["quote"])
                deals = check.query(BuyRequestDeal).all()
                if "selected" in results:
                    self.assertEqual(len(deals), 1)
                    self.assertEqual(quote.status, "coordination_requested")
                    self.assertEqual(revision.status, "selected")
                    self.assertEqual(deals[0].selected_revision_id, revision.id)
                else:
                    self.assertEqual(deals, [])
                    self.assertEqual(quote.status, "withdrawn")
                    self.assertEqual(revision.status, "withdrawn")
            finally:
                check.close()
                engine.dispose()

    def test_concurrent_supplier_confirm_and_decline_leave_one_coherent_state(self):
        with tempfile.TemporaryDirectory() as tempdir:
            engine, Session, ids = self._seed_concurrent_negotiation_database(
                Path(tempdir) / "supplier-decision.db"
            )
            seed = Session()
            try:
                request = seed.get(BuyRequest, ids["request"])
                quote = seed.get(BuyRequestQuote, ids["quote"])
                buyer = seed.get(User, ids["buyer"])
                deal = matchmaking.select_quote(seed, request, quote, buyer)
                seed.commit()
                deal_id = deal.id
            finally:
                seed.close()

            start = threading.Barrier(2)
            decision_lock = threading.Lock()
            both_decisions_loaded = threading.Event()
            decision_count = 0
            original_decision = matchmaking.supplier_decision

            def synchronized_decision(*args, **kwargs):
                nonlocal decision_count
                with decision_lock:
                    decision_count += 1
                    if decision_count == 2:
                        both_decisions_loaded.set()
                # Before the fix both requests can load buyer_selected and enter
                # here together. After BEGIN IMMEDIATE, the first request owns
                # the write transaction and the second reaches this point only
                # after the first one commits.
                both_decisions_loaded.wait(timeout=0.25)
                return original_decision(*args, **kwargs)

            def decide(confirm: bool) -> str:
                db = Session()
                try:
                    supplier_user = db.get(User, ids["supplier_user"])
                    start.wait(timeout=5)
                    endpoint = (
                        buy_request_router.supplier_confirm_deal
                        if confirm
                        else buy_request_router.supplier_decline_deal
                    )
                    endpoint(ids["request"], deal_id, None, supplier_user, db)
                    return "success"
                except BizError:
                    db.rollback()
                    return "conflict"
                except OperationalError:
                    db.rollback()
                    return "database-error"
                finally:
                    db.close()

            with patch.object(
                matchmaking,
                "supplier_decision",
                side_effect=synchronized_decision,
            ):
                with ThreadPoolExecutor(max_workers=2) as pool:
                    confirm_future = pool.submit(decide, True)
                    decline_future = pool.submit(decide, False)
                    results = [confirm_future.result(), decline_future.result()]

            self.assertCountEqual(results, ["success", "conflict"])
            check = Session()
            try:
                deal = check.get(BuyRequestDeal, deal_id)
                request = check.get(BuyRequest, ids["request"])
                quote = check.get(BuyRequestQuote, ids["quote"])
                decision_events = check.query(BuyRequestEvent).filter(
                    BuyRequestEvent.deal_id == deal_id,
                    BuyRequestEvent.event_type.in_(("supplier_confirmed", "supplier_declined")),
                ).all()
                self.assertEqual(len(decision_events), 1)
                if deal.status == "platform_review":
                    self.assertEqual(deal.active_slot, f"request:{ids['request']}")
                    self.assertEqual(request.status, "platform_review")
                    self.assertEqual(quote.status, "coordination_requested")
                    self.assertEqual(decision_events[0].event_type, "supplier_confirmed")
                else:
                    self.assertEqual(deal.status, "supplier_declined")
                    self.assertIsNone(deal.active_slot)
                    self.assertEqual(request.status, "published")
                    self.assertEqual(quote.status, "withdrawn")
                    self.assertEqual(decision_events[0].event_type, "supplier_declined")
            finally:
                check.close()
                engine.dispose()

    def test_concurrent_quote_creation_keeps_one_active_supplier_quote(self):
        with tempfile.TemporaryDirectory() as tempdir:
            database = Path(tempdir) / "concurrent-quotes.db"
            engine = create_engine(
                f"sqlite:///{database}",
                connect_args={"check_same_thread": False, "timeout": 10},
            )
            Base.metadata.create_all(engine)
            Session = sessionmaker(bind=engine, expire_on_commit=False)
            seed = Session()
            buyer = User(username="并发采购方", phone="13921000001", password="!")
            supplier_user = User(
                username="并发报价商家",
                phone="13921000002",
                password="!",
                role="supplier",
                supplier_status="approved",
            )
            seed.add_all([buyer, supplier_user])
            seed.flush()
            supplier = Supplier(
                user_id=supplier_user.id,
                company_name="并发报价商家",
                contact="报价联系人",
                phone=supplier_user.phone,
                status="approved",
            )
            seed.add(supplier)
            seed.flush()
            request = BuyRequest(
                user_id=buyer.id,
                request_type="online",
                gpu_model="H100 80GB",
                quantity=1,
                gpu_hours=24,
                currency="CNY",
                requirements={},
                status="published",
                expires_at=datetime.now(timezone.utc).replace(tzinfo=None) + timedelta(days=1),
            )
            seed.add(request)
            seed.commit()
            request_id = request.id
            supplier_user_id = supplier_user.id
            seed.close()
            barrier = threading.Barrier(2)

            def quote(total_price: float) -> str:
                db = Session()
                try:
                    local_user = db.get(User, supplier_user_id)
                    barrier.wait(timeout=5)
                    buy_request_router.create_quote(
                        request_id,
                        buy_request_router.QuoteIn(
                            unit_price=4.2,
                            total_price=total_price,
                            currency="CNY",
                            message="并发报价",
                            expires_in_hours=24,
                        ),
                        local_user,
                        db,
                    )
                    return "created"
                except BizError as exc:
                    db.rollback()
                    return exc.msg
                finally:
                    db.close()

            with ThreadPoolExecutor(max_workers=2) as pool:
                results = sorted(pool.map(quote, (100.0, 101.0)))

            check = Session()
            self.assertEqual(results, ["created", "已经提交过有效报价"])
            self.assertEqual(check.query(BuyRequestQuote).count(), 1)
            self.assertEqual(check.query(BuyRequestQuoteRevision).count(), 1)
            self.assertEqual(check.query(BuyRequestEvent).filter(
                BuyRequestEvent.event_type == "quote_submitted",
            ).count(), 1)
            check.close()
            engine.dispose()

    def test_concurrent_selection_creates_only_one_active_deal(self):
        with tempfile.TemporaryDirectory() as tempdir:
            database = Path(tempdir) / "matchmaking.db"
            engine = create_engine(
                f"sqlite:///{database}",
                connect_args={"check_same_thread": False, "timeout": 10},
            )
            Base.metadata.create_all(engine)
            Session = sessionmaker(bind=engine, expire_on_commit=False)
            seed = Session()
            buyer = User(username="并发买家", phone="13920000001", password="!")
            supplier_user_a = User(
                username="并发商家A", phone="13920000002", password="!",
                role="supplier", supplier_status="approved",
            )
            supplier_user_b = User(
                username="并发商家B", phone="13920000003", password="!",
                role="supplier", supplier_status="approved",
            )
            seed.add_all([buyer, supplier_user_a, supplier_user_b])
            seed.flush()
            supplier_a = Supplier(
                user_id=supplier_user_a.id, company_name="并发甲", contact="甲",
                phone=supplier_user_a.phone, status="approved",
            )
            supplier_b = Supplier(
                user_id=supplier_user_b.id, company_name="并发乙", contact="乙",
                phone=supplier_user_b.phone, status="approved",
            )
            seed.add_all([supplier_a, supplier_b])
            seed.flush()
            request = BuyRequest(
                user_id=buyer.id, request_type="online", gpu_model="A100",
                quantity=1, gpu_hours=24, currency="CNY", requirements={},
                status="quoting",
                expires_at=datetime.now(timezone.utc).replace(tzinfo=None) + timedelta(days=1),
            )
            seed.add(request)
            seed.flush()
            quotes = []
            for supplier, supplier_user, total in (
                (supplier_a, supplier_user_a, "100"),
                (supplier_b, supplier_user_b, "101"),
            ):
                quote = BuyRequestQuote(
                    buy_request_id=request.id,
                    supplier_id=supplier.id,
                    total_price=Decimal(total),
                    currency="CNY",
                    status="active",
                    expires_at=datetime.now(timezone.utc).replace(tzinfo=None) + timedelta(days=1),
                )
                seed.add(quote)
                seed.flush()
                seed.add(BuyRequestQuoteRevision(
                    quote_id=quote.id,
                    buy_request_id=request.id,
                    supplier_id=supplier.id,
                    revision_number=1,
                    proposer_role="supplier",
                    proposer_user_id=supplier_user.id,
                    total_price=quote.total_price,
                    currency="CNY",
                    expires_at=quote.expires_at,
                    status="active",
                ))
                quotes.append(quote.id)
            seed.commit()
            request_id, buyer_id = request.id, buyer.id
            seed.close()
            barrier = threading.Barrier(2)

            def select(quote_id: int) -> str:
                db = Session()
                try:
                    local_request = db.get(BuyRequest, request_id)
                    local_quote = db.get(BuyRequestQuote, quote_id)
                    local_buyer = db.get(User, buyer_id)
                    barrier.wait(timeout=5)
                    matchmaking.select_quote(db, local_request, local_quote, local_buyer)
                    db.commit()
                    return "ok"
                except BizError:
                    db.rollback()
                    return "conflict"
                finally:
                    db.close()

            with ThreadPoolExecutor(max_workers=2) as pool:
                results = sorted(pool.map(select, quotes))

            check = Session()
            self.assertEqual(results, ["conflict", "ok"])
            self.assertEqual(check.query(BuyRequestDeal).count(), 1)
            self.assertEqual(check.query(BuyRequestDeal).filter(
                BuyRequestDeal.active_slot.isnot(None),
            ).count(), 1)
            check.close()
            engine.dispose()

    def test_legacy_quote_revision_migration_is_additive_and_idempotent(self):
        request = self._request()
        quote = BuyRequestQuote(
            buy_request_id=request.id,
            supplier_id=self.supplier.id,
            total_price=Decimal("88.00"),
            currency="CNY",
            message="历史报价",
            status="active",
        )
        self.db.add(quote)
        self.db.commit()
        self.assertEqual(self.db.query(BuyRequestQuoteRevision).filter(
            BuyRequestQuoteRevision.quote_id == quote.id,
        ).count(), 0)

        _migrate_buy_request_quote_revisions(self.db)
        _migrate_buy_request_quote_revisions(self.db)

        revision = self.db.query(BuyRequestQuoteRevision).filter(
            BuyRequestQuoteRevision.quote_id == quote.id,
        ).one()
        self.assertEqual(revision.revision_number, 1)
        self.assertEqual(revision.proposer_user_id, self.supplier_user.id)
        self.assertEqual(revision.total_price, Decimal("88.00"))

if __name__ == "__main__":
    unittest.main()
