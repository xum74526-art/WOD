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
from app.db.base import Base
from app.db.session import get_db
from app.models import (  # noqa: F401
    BankCard,
    Order,
    PaymentOrder,
    Post,
    Product,
    User,
    Verification,
    Wallet,
    WithdrawalOrder,
)
from app.routers import admin as admin_router
from app.routers import community as community_router
from app.routers import finance as finance_router
from app.services.auth_session import create_authenticated_session
from app.utils.response import BizError, error


class AdminPlatformFilterTests(unittest.TestCase):
    def setUp(self):
        engine = create_engine(
            "sqlite://",
            connect_args={"check_same_thread": False},
            poolclass=StaticPool,
        )
        Base.metadata.create_all(engine)
        self.db = sessionmaker(bind=engine)()
        self.original_secret = settings.SECRET_KEY
        settings.SECRET_KEY = "admin-platform-filter-test-secret"

        self.admin = User(
            phone="13900000001",
            username="平台管理员",
            password="!",
            role="admin",
            created_platform="admin",
        )
        self.web_user = User(
            phone="13900000002",
            username="Web 用户",
            password="!",
            created_platform="web",
        )
        self.android_user = User(
            phone="13900000003",
            username="Android 用户",
            password="!",
            role="supplier",
            created_platform="android",
        )
        self.db.add_all([self.admin, self.web_user, self.android_user])
        self.db.flush()

        product = Product(
            name="测试 GPU",
            gpu_model="RTX 4090",
            memory="24GB",
            price=Decimal("1.2"),
            stock=2,
            status="on",
        )
        self.db.add(product)
        self.db.flush()
        expires_at = datetime.now(timezone.utc).replace(tzinfo=None) + timedelta(minutes=30)
        for index, (user, platform) in enumerate(
            ((self.web_user, "web"), (self.android_user, "android")),
            start=1,
        ):
            wallet = Wallet(
                user_id=user.id,
                balance=Decimal("10"),
                frozen=Decimal("0"),
                withdrawable_balance=Decimal("5"),
                withdraw_frozen=Decimal("0"),
            )
            self.db.add(wallet)
            self.db.flush()
            card = BankCard(
                user_id=user.id,
                bank_name="测试银行",
                card_number=f"45395787636214{index:02d}",
                holder="测试用户",
                status="registered",
                verification_mode="format_only",
                created_platform=platform,
                last_modified_platform=platform,
            )
            self.db.add(card)
            self.db.flush()
            self.db.add_all([
                Order(
                    order_no=f"ADMIN-ORDER-{index}",
                    user_id=user.id,
                    product_id=product.id,
                    quantity=1,
                    purchase_hours=2,
                    cycle_days=1,
                    amount=Decimal("2.4"),
                    status="running",
                    created_platform=platform,
                    last_modified_platform=platform,
                ),
                PaymentOrder(
                    order_no=f"ADMIN-PAY-{index}",
                    user_id=user.id,
                    provider="qixiangpay",
                    status="pending",
                    amount_cny=Decimal("1"),
                    card_hours=Decimal("0.998004"),
                    card_hour_rate=Decimal("1.002"),
                    checkout_token_hash=f"checkout-{index}",
                    expires_at=expires_at,
                    created_platform=platform,
                    last_modified_platform=platform,
                ),
                Verification(
                    user_id=user.id,
                    real_name="测试用户",
                    id_card="11010519491231002X",
                    status="pending",
                    created_platform=platform,
                    last_modified_platform=platform,
                ),
                WithdrawalOrder(
                    order_no=f"ADMIN-WITHDRAW-{index}",
                    user_id=user.id,
                    wallet_id=wallet.id,
                    bank_card_id=card.id,
                    client_request_id=f"admin-filter-withdraw-{index}",
                    status="reviewing",
                    amount_card_hours=Decimal("1"),
                    locked_rate_cny=Decimal("1.002"),
                    gross_amount_cny=Decimal("1.00"),
                    fee_cny=Decimal("0"),
                    net_amount_cny=Decimal("1.00"),
                    bank_name_snapshot="测试银行",
                    card_last4_snapshot=f"14{index:02d}",
                    holder_snapshot="测试用户",
                    created_platform=platform,
                    last_modified_platform=platform,
                ),
            ])
        self.db.commit()

        issued = create_authenticated_session(
            self.db,
            self.admin,
            platform="admin",
            client_id="admin",
            auth_method="test",
        )
        personal_issued = create_authenticated_session(
            self.db,
            self.web_user,
            platform="web",
            client_id="web",
            auth_method="test",
        )
        supplier_issued = create_authenticated_session(
            self.db,
            self.android_user,
            platform="android",
            client_id="android",
            auth_method="test",
        )
        app = FastAPI()

        @app.exception_handler(BizError)
        async def biz_handler(request: Request, exc: BizError):
            return JSONResponse(
                status_code=exc.status_code,
                content=error(exc.msg, exc.code),
            )

        app.include_router(admin_router.router)
        app.include_router(finance_router.router)

        def db_override():
            yield self.db

        app.dependency_overrides[get_db] = db_override
        self.client = TestClient(app)
        self.headers = {"Authorization": f"Bearer {issued.token}"}
        self.non_admin_headers = (
            {"Authorization": f"Bearer {personal_issued.token}"},
            {"Authorization": f"Bearer {supplier_issued.token}"},
        )

    def tearDown(self):
        self.client.close()
        settings.SECRET_KEY = self.original_secret
        self.db.close()

    def _items(self, path: str) -> list[dict]:
        response = self.client.get(path, headers=self.headers)
        self.assertEqual(response.status_code, 200, response.text)
        return response.json()["data"]["items"]

    def test_admin_business_lists_filter_and_expose_created_platform(self):
        for path in (
            "/api/admin/users?platform=web",
            "/api/admin/orders?platform=web",
            "/api/admin/recharge-orders?platform=web",
        ):
            items = self._items(path)
            self.assertEqual(len(items), 1, path)
            self.assertEqual(items[0]["created_platform"], "web", path)

        overview = self.client.get(
            "/api/admin/overview?platform=web", headers=self.headers
        )
        self.assertEqual(overview.status_code, 200, overview.text)
        data = overview.json()["data"]
        self.assertEqual(data["created_platform"], "web")
        self.assertEqual(set(data["counts"].values()), {1})
        self.assertEqual(data["by_platform"][0]["created_platform"], "web")

    def test_finance_lists_filter_and_expose_created_platform(self):
        for path in (
            "/api/finance/verifications?platform=web",
            "/api/finance/bank-cards?platform=web",
            "/api/finance/withdrawals?platform=web",
        ):
            items = self._items(path)
            self.assertEqual(len(items), 1, path)
            self.assertEqual(items[0]["created_platform"], "web", path)

    def test_only_platform_admin_can_access_finance_reviews(self):
        admin_access = self.client.get("/api/finance/me", headers=self.headers)
        self.assertEqual(admin_access.status_code, 200, admin_access.text)
        self.assertTrue(admin_access.json()["data"]["is_admin"])

        for headers in self.non_admin_headers:
            access = self.client.get("/api/finance/me", headers=headers)
            self.assertEqual(access.status_code, 200, access.text)
            self.assertFalse(access.json()["data"]["is_admin"])
            response = self.client.get("/api/finance/verifications", headers=headers)
            self.assertEqual(response.status_code, 403, response.text)

    def test_unknown_or_system_platform_filter_is_rejected(self):
        for platform in ("system", "forged"):
            response = self.client.get(
                f"/api/admin/orders?platform={platform}", headers=self.headers
            )
            self.assertEqual(response.status_code, 422)


class SpoofedPlatformHeaderTests(unittest.TestCase):
    def test_arbitrary_headers_do_not_override_server_session_platform(self):
        engine = create_engine(
            "sqlite://",
            connect_args={"check_same_thread": False},
            poolclass=StaticPool,
        )
        Base.metadata.create_all(engine)
        db = sessionmaker(bind=engine)()
        original_secret = settings.SECRET_KEY
        settings.SECRET_KEY = "spoofed-platform-header-test-secret"
        try:
            user = User(
                phone="13900000011",
                username="来源头测试",
                password="!",
                created_platform="web",
            )
            db.add(user)
            db.commit()
            db.refresh(user)
            issued = create_authenticated_session(
                db,
                user,
                platform="web",
                client_id="web",
                auth_method="test",
            )
            app = FastAPI()
            app.include_router(community_router.router)

            def db_override():
                yield db

            app.dependency_overrides[get_db] = db_override
            client = TestClient(app)
            try:
                response = client.post(
                    "/api/community/posts",
                    json={"content": "请求头不能伪造来源"},
                    headers={
                        "Authorization": f"Bearer {issued.token}",
                        "X-Platform": "android",
                        "X-Client-Id": "android",
                    },
                )
                self.assertEqual(response.status_code, 200, response.text)
                row = db.query(Post).one()
                self.assertEqual(row.created_platform, "web")
            finally:
                client.close()
        finally:
            settings.SECRET_KEY = original_secret
            db.close()


if __name__ == "__main__":
    unittest.main()
