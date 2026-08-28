import unittest
from datetime import datetime, timedelta, timezone
from decimal import Decimal

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.core.config import settings
from app.core.deps import get_current_user
from app.db.base import Base
from app.db.session import get_db
from app.models import BuyRequest, BuyRequestQuote, Ledger, Order, Supplier, User, Wallet
from app.routers import buy_request as buy_request_router
from app.utils.response import BizError, error


class BuyRequestVisibilityTests(unittest.TestCase):
    def setUp(self):
        self.original_direct_trade = settings.DIRECT_TRADE_ENABLED
        self.original_matchmaking = settings.MATCHMAKING_ENABLED
        settings.DIRECT_TRADE_ENABLED = False
        settings.MATCHMAKING_ENABLED = True
        self.engine = create_engine(
            "sqlite://",
            connect_args={"check_same_thread": False},
            poolclass=StaticPool,
        )
        Base.metadata.create_all(self.engine)
        self.db = sessionmaker(bind=self.engine)()

        self.buyer = User(
            username="采购用户",
            phone="13800001001",
            password="!",
            role="personal",
        )
        self.supplier_user = User(
            username="供应商一",
            phone="13800001002",
            password="!",
            role="supplier",
            supplier_status="approved",
        )
        self.other_supplier_user = User(
            username="供应商二",
            phone="13800001003",
            password="!",
            role="supplier",
            supplier_status="approved",
        )
        self.admin = User(
            username="平台管理员",
            phone="13800001004",
            password="!",
            role="admin",
        )
        self.db.add_all([
            self.buyer,
            self.supplier_user,
            self.other_supplier_user,
            self.admin,
        ])
        self.db.flush()
        self.supplier = Supplier(
            user_id=self.supplier_user.id,
            company_name="一号算力商家",
            contact="商家一",
            phone=self.supplier_user.phone,
            status="approved",
        )
        self.other_supplier = Supplier(
            user_id=self.other_supplier_user.id,
            company_name="二号算力商家",
            contact="商家二",
            phone=self.other_supplier_user.phone,
            status="approved",
        )
        self.db.add_all([self.supplier, self.other_supplier])
        self.db.flush()

        self.open_request = self._add_request(self.buyer, "开放市场需求", {})
        self.targeted_to_me = self._add_request(
            self.buyer,
            "定向一号商家",
            {"supplier_id": self.supplier.id, "product_id": 11},
        )
        self.targeted_elsewhere = self._add_request(
            self.buyer,
            "定向二号商家",
            {"supplier_id": str(self.other_supplier.id), "product_id": 22},
        )
        self.own_request = self._add_request(
            self.supplier_user,
            "商家自己的需求",
            {"supplier_id": self.other_supplier.id},
        )
        self.db.add(BuyRequestQuote(
            buy_request_id=self.targeted_to_me.id,
            supplier_id=self.supplier.id,
            total_price=Decimal("120.00"),
            currency="CNY",
            message="人工确认方案",
            status="active",
        ))
        self.db.commit()

        self.current_user = self.supplier_user
        app = FastAPI()

        @app.exception_handler(BizError)
        async def biz_error_handler(request: Request, exc: BizError):
            del request
            return JSONResponse(
                status_code=exc.status_code,
                content=error(exc.msg, exc.code),
            )

        def db_override():
            yield self.db

        app.include_router(buy_request_router.router)
        app.include_router(buy_request_router.admin_router)
        app.dependency_overrides[get_db] = db_override
        app.dependency_overrides[get_current_user] = lambda: self.current_user
        self.client = TestClient(app)

    def tearDown(self):
        settings.DIRECT_TRADE_ENABLED = self.original_direct_trade
        settings.MATCHMAKING_ENABLED = self.original_matchmaking
        self.client.close()
        self.db.close()
        self.engine.dispose()

    def _add_request(self, owner: User, label: str, requirements: dict) -> BuyRequest:
        item = BuyRequest(
            user_id=owner.id,
            request_type="online",
            gpu_model=label,
            quantity=1,
            gpu_hours=24,
            currency="CNY",
            requirements=requirements,
            contact=f"{label}联系人",
            phone=owner.phone,
            status="published",
            expires_at=datetime.now(timezone.utc).replace(tzinfo=None) + timedelta(days=1),
        )
        self.db.add(item)
        self.db.flush()
        return item

    def _get(self, path: str):
        response = self.client.get(path)
        self.assertEqual(response.status_code, 200, response.text)
        return response.json()["data"]

    def test_short_contact_number_is_never_exposed_to_a_supplier(self):
        self.assertEqual(buy_request_router._mask_phone("12345"), "****")
        self.assertIsNone(buy_request_router._mask_phone(None))

    def test_supplier_list_shows_open_targeted_and_own_but_not_other_target(self):
        rows = self._get("/api/buy-requests?request_type=online&view=seller")
        by_id = {row["id"]: row for row in rows}

        self.assertEqual(
            set(by_id),
            {self.open_request.id, self.targeted_to_me.id, self.own_request.id},
        )
        self.assertFalse(by_id[self.open_request.id]["targeted_to_me"])
        self.assertIsNone(by_id[self.open_request.id]["targeted_supplier_id"])
        self.assertTrue(by_id[self.targeted_to_me.id]["targeted_to_me"])
        self.assertEqual(
            by_id[self.targeted_to_me.id]["target_supplier"],
            {"id": self.supplier.id, "company_name": "一号算力商家"},
        )
        self.assertTrue(by_id[self.own_request.id]["is_own"])
        self.assertEqual(by_id[self.own_request.id]["contact"], "商家自己的需求联系人")
        self.assertEqual(by_id[self.own_request.id]["phone"], self.supplier_user.phone)
        self.assertIsNone(by_id[self.targeted_to_me.id]["contact"])
        self.assertIsNone(by_id[self.targeted_to_me.id]["phone"])
        self.assertIsNone(by_id[self.targeted_to_me.id]["user_id"])
        self.assertIsNone(by_id[self.targeted_to_me.id]["buyer_name"])

    def test_supplier_cannot_read_or_quote_request_targeted_elsewhere(self):
        detail = self.client.get(f"/api/buy-requests/{self.targeted_elsewhere.id}")
        self.assertEqual(detail.status_code, 404, detail.text)

        quote = self.client.post(
            f"/api/buy-requests/{self.targeted_elsewhere.id}/quotes",
            json={"total_price": 10, "currency": "CNY"},
        )
        self.assertEqual(quote.status_code, 404, quote.text)

    def test_own_request_is_readable_in_seller_view_but_cannot_be_quoted(self):
        detail = self._get(f"/api/buy-requests/{self.own_request.id}")
        self.assertTrue(detail["request"]["is_own"])
        self.assertEqual(detail["request"]["contact"], "商家自己的需求联系人")

        quote = self.client.post(
            f"/api/buy-requests/{self.own_request.id}/quotes",
            json={"total_price": 10, "currency": "CNY"},
        )
        self.assertEqual(quote.status_code, 400, quote.text)
        self.assertEqual(quote.json()["msg"], "不能给自己的求购报价")

    def test_targeted_supplier_detail_masks_buyer_contact(self):
        detail = self._get(f"/api/buy-requests/{self.targeted_to_me.id}")
        row = detail["request"]
        self.assertFalse(row["is_own"])
        self.assertTrue(row["targeted_to_me"])
        self.assertIsNone(row["contact"])
        self.assertIsNone(row["phone"])
        self.assertIsNone(row["user_id"])
        self.assertIsNone(row["buyer_name"])
        self.assertEqual(len(detail["quotes"]), 1)

    def test_supplier_can_read_own_quote_history_but_cannot_requote_closed_request(self):
        self.targeted_to_me.status = "closed"
        self.db.commit()

        rows = self._get("/api/buy-requests?request_type=online&view=seller")
        self.assertIn(self.targeted_to_me.id, {row["id"] for row in rows})
        detail = self._get(f"/api/buy-requests/{self.targeted_to_me.id}")
        self.assertEqual(len(detail["quotes"]), 1)
        quote = self.client.post(
            f"/api/buy-requests/{self.targeted_to_me.id}/quotes",
            json={"total_price": 10, "currency": "CNY"},
        )
        self.assertEqual(quote.status_code, 400, quote.text)

    def test_admin_can_list_filter_and_read_full_request_details(self):
        self.current_user = self.admin
        page = self._get(
            "/api/admin/buy-requests?status=published&request_type=online&page=1&page_size=2"
        )
        self.assertEqual(page["total"], 4)
        self.assertEqual(page["page"], 1)
        self.assertEqual(page["page_size"], 2)
        self.assertEqual(len(page["items"]), 2)
        self.assertTrue(all(item["contact"] and item["phone"] for item in page["items"]))

        keyword_page = self._get("/api/admin/buy-requests?keyword=定向二号")
        self.assertEqual(keyword_page["total"], 1)
        listed = keyword_page["items"][0]
        self.assertEqual(listed["id"], self.targeted_elsewhere.id)
        self.assertEqual(listed["targeted_supplier_id"], self.other_supplier.id)
        self.assertEqual(
            listed["target_supplier"],
            {"id": self.other_supplier.id, "company_name": "二号算力商家"},
        )

        detail = self._get(f"/api/admin/buy-requests/{self.targeted_to_me.id}")
        self.assertEqual(detail["request"]["contact"], "定向一号商家联系人")
        self.assertEqual(detail["request"]["phone"], self.buyer.phone)
        self.assertEqual(len(detail["quotes"]), 1)

    def test_non_admin_cannot_use_admin_request_endpoints(self):
        for path in (
            "/api/admin/buy-requests",
            f"/api/admin/buy-requests/{self.targeted_to_me.id}",
        ):
            with self.subTest(path=path):
                response = self.client.get(path)
                self.assertEqual(response.status_code, 403, response.text)

    def test_matching_selection_requests_platform_coordination_without_financial_writes(self):
        self.current_user = self.buyer
        before = (
            self.db.query(Order).count(),
            self.db.query(Wallet).count(),
            self.db.query(Ledger).count(),
        )
        selected_quote = self.db.query(BuyRequestQuote).filter(
            BuyRequestQuote.buy_request_id == self.targeted_to_me.id,
        ).one()

        response = self.client.post(
            f"/api/buy-requests/{self.targeted_to_me.id}/quotes/{selected_quote.id}/select"
        )
        self.assertEqual(response.status_code, 200, response.text)
        payload = response.json()["data"]
        self.assertEqual(payload["status"], "buyer_selected")
        self.assertEqual(payload["quote_status"], "coordination_requested")
        self.assertEqual(payload["commerce_mode"], "matchmaking")
        self.assertEqual(payload["deal"]["status"], "buyer_selected")

        self.db.refresh(self.targeted_to_me)
        self.db.refresh(selected_quote)
        self.assertEqual(self.targeted_to_me.status, "buyer_selected")
        self.assertEqual(selected_quote.status, "coordination_requested")
        self.assertEqual(before, (
            self.db.query(Order).count(),
            self.db.query(Wallet).count(),
            self.db.query(Ledger).count(),
        ))

        retry = self.client.post(
            f"/api/buy-requests/{self.targeted_to_me.id}/quotes/{selected_quote.id}/select"
        )
        self.assertEqual(retry.status_code, 200, retry.text)
        self.assertEqual(retry.json()["data"]["status"], "buyer_selected")

    def test_direct_trade_selection_retains_legacy_selected_statuses(self):
        settings.DIRECT_TRADE_ENABLED = True
        self.current_user = self.buyer
        quote = self.db.query(BuyRequestQuote).filter(
            BuyRequestQuote.buy_request_id == self.targeted_to_me.id,
        ).one()

        response = self.client.post(
            f"/api/buy-requests/{self.targeted_to_me.id}/quotes/{quote.id}/select"
        )
        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(response.json()["data"]["status"], "quote_selected")
        self.assertEqual(response.json()["data"]["quote_status"], "selected")

    def test_matchmaking_switch_blocks_new_requests_and_quotes(self):
        settings.MATCHMAKING_ENABLED = False
        self.current_user = self.buyer
        created = self.client.post("/api/buy-requests", json={
            "request_type": "online",
            "gpu_model": "A100",
            "quantity": 1,
            "gpu_hours": 24,
            "currency": "CNY",
        })
        self.assertEqual(created.status_code, 409, created.text)

        self.current_user = self.supplier_user
        quoted = self.client.post(
            f"/api/buy-requests/{self.open_request.id}/quotes",
            json={"total_price": 100, "currency": "CNY"},
        )
        self.assertEqual(quoted.status_code, 409, quoted.text)


if __name__ == "__main__":
    unittest.main()
