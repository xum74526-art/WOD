import unittest

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, inspect, text
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.core.config import settings
from app.db.base import Base
from app.db.session import get_db
from app.models import ComputeOnboarding, Notification, User, Verification
from app.routers import admin as admin_router
from app.routers import onboarding as onboarding_router
from app.services.auth_session import create_authenticated_session
from app.utils.response import BizError, error
import init_db


class AdminOnboardingTests(unittest.TestCase):
    def setUp(self):
        self.engine = create_engine(
            "sqlite://",
            connect_args={"check_same_thread": False},
            poolclass=StaticPool,
        )
        Base.metadata.create_all(self.engine)
        self.db = sessionmaker(bind=self.engine, expire_on_commit=False)()
        self.original_secret = settings.SECRET_KEY
        settings.SECRET_KEY = "admin-onboarding-test-secret"

        self.admin = User(
            phone="13900002701", username="托管管理员", password="!", role="admin"
        )
        self.user = User(
            phone="13900002702", username="托管申请人", password="!"
        )
        self.db.add_all([self.admin, self.user])
        self.db.flush()
        self.application = ComputeOnboarding(
            user_id=self.user.id,
            entity_type="personal",
            contact="许先生",
            phone="13900002702",
            device_model="RTX 4090",
            device_count=2,
            location="上海",
            remark="两台自有设备",
            created_platform="android",
            last_modified_platform="android",
        )
        self.db.add(self.application)
        self.db.add(Verification(
            user_id=self.user.id,
            real_name="托管申请人",
            id_card="test-only-protected-id",
            status="verified",
        ))
        self.db.commit()

        admin_session = create_authenticated_session(
            self.db,
            self.admin,
            platform="admin",
            client_id="admin",
            auth_method="test",
        )
        user_session = create_authenticated_session(
            self.db,
            self.user,
            platform="web",
            client_id="web",
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
        app.include_router(onboarding_router.router)

        def db_override():
            yield self.db

        app.dependency_overrides[get_db] = db_override
        self.client = TestClient(app)
        self.admin_headers = {"Authorization": f"Bearer {admin_session.token}"}
        self.user_headers = {"Authorization": f"Bearer {user_session.token}"}

    def tearDown(self):
        self.client.close()
        self.db.close()
        self.engine.dispose()
        settings.SECRET_KEY = self.original_secret

    def review(self, status: str, expected_version: int, note: str | None = None):
        return self.client.post(
            f"/api/admin/onboardings/{self.application.id}/review",
            headers=self.admin_headers,
            json={
                "status": status,
                "expected_version": expected_version,
                "note": note,
            },
        )

    def test_admin_queue_filters_and_non_admin_is_denied(self):
        denied = self.client.get(
            "/api/admin/onboardings", headers=self.user_headers
        )
        self.assertEqual(denied.status_code, 403, denied.text)

        response = self.client.get(
            "/api/admin/onboardings",
            params={
                "status": "submitted",
                "entity_type": "personal",
                "platform": "android",
                "keyword": "4090",
                "page": 1,
                "page_size": 20,
            },
            headers=self.admin_headers,
        )
        self.assertEqual(response.status_code, 200, response.text)
        data = response.json()["data"]
        self.assertEqual(data["total"], 1)
        self.assertEqual(data["items"][0]["username"], self.user.username)
        self.assertEqual(data["items"][0]["version"], 1)

    def test_admin_decision_reaches_user_and_terminal_state_is_protected(self):
        contacted = self.review("contacted", 1, "已电话联系，等待设备清单")
        self.assertEqual(contacted.status_code, 200, contacted.text)
        self.assertEqual(contacted.json()["data"]["version"], 2)

        stale = self.review("approved", 1, "旧页面重复提交")
        self.assertEqual(stale.status_code, 409, stale.text)

        approved = self.review("approved", 2, "资料齐全，进入接入安排")
        self.assertEqual(approved.status_code, 200, approved.text)
        result = approved.json()["data"]
        self.assertEqual(result["status"], "approved")
        self.assertEqual(result["last_modified_platform"], "admin")
        self.assertEqual(result["version"], 3)

        mine = self.client.get("/api/onboarding/mine", headers=self.user_headers)
        self.assertEqual(mine.status_code, 200, mine.text)
        mine_item = mine.json()["data"][0]
        self.assertEqual(mine_item["status"], "approved")
        self.assertEqual(mine_item["review_note"], "资料齐全，进入接入安排")
        self.assertEqual(mine_item["version"], 3)

        notices = self.db.query(Notification).filter_by(user_id=self.user.id).all()
        self.assertEqual(len(notices), 2)
        self.assertEqual(notices[-1].action_url, "/pages/compute-onboarding/index")

        terminal = self.review("rejected", 3, "不应允许改写终态")
        self.assertEqual(terminal.status_code, 409, terminal.text)

    def test_rejection_requires_customer_visible_reason(self):
        response = self.review("rejected", 1, "")
        self.assertEqual(response.status_code, 422, response.text)
        self.db.refresh(self.application)
        self.assertEqual(self.application.status, "submitted")

    def test_user_submission_records_trusted_platform_and_validates_input(self):
        response = self.client.post(
            "/api/onboarding",
            headers=self.user_headers,
            json={
                "entity_type": "personal",
                "contact": "  新联系人  ",
                "phone": "13900002702",
                "device_model": "  A100 80GB  ",
                "device_count": 4,
                "location": "北京",
                "remark": "测试机柜",
            },
        )
        self.assertEqual(response.status_code, 200, response.text)
        data = response.json()["data"]
        self.assertEqual(data["contact"], "新联系人")
        self.assertEqual(data["device_model"], "A100 80GB")
        self.assertEqual(data["created_platform"], "web")
        self.assertEqual(data["last_modified_platform"], "web")
        self.assertEqual(data["version"], 1)

        invalid = self.client.post(
            "/api/onboarding",
            headers=self.user_headers,
            json={
                "entity_type": "personal",
                "contact": "   ",
                "phone": "1",
                "device_model": "",
                "device_count": 0,
            },
        )
        self.assertEqual(invalid.status_code, 422, invalid.text)

    def test_legacy_onboarding_table_gets_review_and_audit_columns(self):
        legacy_engine = create_engine("sqlite://")
        with legacy_engine.begin() as connection:
            connection.execute(text(
                "CREATE TABLE compute_onboardings ("
                "id INTEGER PRIMARY KEY, status VARCHAR(16))"
            ))
            connection.execute(text(
                "INSERT INTO compute_onboardings (id, status) VALUES (1, 'submitted')"
            ))

        init_db._ensure_columns(legacy_engine)

        columns = {column["name"] for column in inspect(legacy_engine).get_columns("compute_onboardings")}
        self.assertTrue({
            "review_note", "reviewed_by", "reviewed_at", "updated_at",
            "created_platform", "last_modified_platform", "version",
        }.issubset(columns))
        with legacy_engine.connect() as connection:
            row = connection.execute(text(
                "SELECT version, created_platform, last_modified_platform "
                "FROM compute_onboardings WHERE id = 1"
            )).one()
        self.assertEqual(tuple(row), (1, "legacy", "legacy"))
        legacy_engine.dispose()


if __name__ == "__main__":
    unittest.main()
