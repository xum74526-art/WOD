import unittest

from fastapi import HTTPException
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.core.deps import require_admin
from app.db.base import Base
from app.models import Supplier, User, Verification
from app.routers.supplier import SupplierReviewIn, admin_list_applications, admin_review_application
from app.utils.response import BizError


class SupplierAdminTests(unittest.TestCase):
    def setUp(self):
        engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
        Base.metadata.create_all(engine)
        self.db = sessionmaker(bind=engine)()
        self.admin = User(username="平台管理员", phone="13800009001", password="!", role="admin")
        self.applicant = User(username="申请用户", phone="13800009002", password="!", role="personal", supplier_status="pending")
        self.db.add_all([self.admin, self.applicant])
        self.db.flush()
        self.application = Supplier(
            user_id=self.applicant.id,
            company_name="测试商家",
            contact="测试联系人",
            phone="13800009002",
            status="pending",
        )
        self.db.add(self.application)
        self.db.add(Verification(
            user_id=self.applicant.id,
            real_name="申请用户",
            id_card="protected-test-value",
            status="verified",
        ))
        self.db.commit()

    def tearDown(self):
        self.db.close()

    def test_admin_can_list_and_approve_application(self):
        result = admin_list_applications("pending", None, 1, 20, self.admin, self.db)["data"]
        self.assertEqual(result["total"], 1)
        self.assertEqual(result["items"][0]["company_name"], "测试商家")
        self.assertTrue(result["items"][0]["identity_verified"])
        reviewed = admin_review_application(
            self.application.id,
            "approve",
            SupplierReviewIn(),
            self.admin,
            self.db,
        )["data"]
        self.assertEqual(reviewed["status"], "approved")
        self.assertEqual(self.applicant.supplier_status, "approved")
        self.assertEqual(self.applicant.role, "personal")

    def test_unverified_applicant_cannot_be_approved(self):
        applicant = User(
            username="未实名申请用户",
            phone="13800009003",
            password="!",
            supplier_status="pending",
        )
        self.db.add(applicant)
        self.db.flush()
        application = Supplier(
            user_id=applicant.id,
            company_name="未实名商家",
            contact="联系人",
            phone=applicant.phone,
            status="pending",
        )
        self.db.add(application)
        self.db.commit()

        with self.assertRaises(BizError) as unverified:
            admin_review_application(
                application.id,
                "approve",
                SupplierReviewIn(),
                self.admin,
                self.db,
            )
        self.assertEqual(unverified.exception.status_code, 409)
        self.db.refresh(application)
        self.assertEqual(application.status, "pending")

    def test_non_admin_is_rejected(self):
        with self.assertRaises(HTTPException):
            require_admin(self.applicant)

    def test_rejection_requires_reason(self):
        with self.assertRaisesRegex(BizError, "至少 2 个字"):
            admin_review_application(
                self.application.id,
                "reject",
                SupplierReviewIn(note=""),
                self.admin,
                self.db,
            )


if __name__ == "__main__":
    unittest.main()
