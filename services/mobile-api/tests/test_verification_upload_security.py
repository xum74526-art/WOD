import asyncio
import io
import json
import tempfile
import unittest
from datetime import datetime
from pathlib import Path
from unittest.mock import patch

from cryptography.fernet import Fernet
from PIL import Image
from fastapi.exceptions import RequestValidationError
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool
from starlette.datastructures import Headers, UploadFile
from starlette.requests import Request

from app.db.base import Base
from app.core.sensitive import protect
from app.main import request_validation_handler
from app.models import User, Verification
from app.routers import user as user_router
from app.routers import verification as verification_router
from app.utils.response import BizError
from app.schemas.verification import VerificationIn
from app.services.id_card_ocr import OcrPrecheckResult


def image_bytes() -> bytes:
    stream = io.BytesIO()
    Image.new("RGB", (16, 10), color=(240, 240, 240)).save(stream, format="PNG")
    return stream.getvalue()


def jpeg_with_exif_bytes() -> bytes:
    stream = io.BytesIO()
    exif = Image.Exif()
    exif[270] = "private scanner metadata"
    Image.new("RGB", (32, 20), color=(245, 245, 245)).save(
        stream, format="JPEG", exif=exif,
    )
    return stream.getvalue()


def upload_file(content: bytes) -> UploadFile:
    return UploadFile(
        file=io.BytesIO(content),
        filename="id-card.png",
        headers=Headers({"content-type": "image/png"}),
    )


class VerificationUploadSecurityTests(unittest.TestCase):
    def setUp(self):
        self.original_security = {
            "SECRET_KEY": verification_router.settings.SECRET_KEY,
            "SENSITIVE_DATA_KEY": verification_router.settings.SENSITIVE_DATA_KEY,
            "ID_OCR_ENABLED": verification_router.settings.ID_OCR_ENABLED,
        }
        verification_router.settings.SECRET_KEY = "unit-test-id-ocr-secret"
        verification_router.settings.SENSITIVE_DATA_KEY = (
            Fernet.generate_key().decode("ascii")
        )
        verification_router.settings.ID_OCR_ENABLED = False
        engine = create_engine(
            "sqlite://",
            connect_args={"check_same_thread": False},
            poolclass=StaticPool,
        )
        Base.metadata.create_all(engine)
        self.db = sessionmaker(bind=engine)()
        self.user = User(phone="13900000031", username="实名上传测试", password="!")
        self.db.add(self.user)
        self.db.flush()
        self.verification = Verification(
            user_id=self.user.id,
            real_name="张三",
            id_card="protected-test-value",
            status="pending",
            consent_at=datetime(2026, 8, 20, 8, 0, 0),
        )
        self.db.add(self.verification)
        self.db.commit()

    def tearDown(self):
        self.db.close()
        for name, value in self.original_security.items():
            setattr(verification_router.settings, name, value)

    def test_identity_directory_uses_same_private_persistent_upload_root(self):
        self.assertEqual(verification_router.UPLOAD_ROOT, user_router.UPLOAD_ROOT)
        self.assertEqual(verification_router.UPLOAD_DIR, user_router.UPLOAD_ROOT / "id_cards")

    def test_two_valid_images_are_atomically_saved_without_temp_files(self):
        with tempfile.TemporaryDirectory() as temp_dir, patch.object(
            verification_router, "UPLOAD_DIR", Path(temp_dir),
        ):
            result = asyncio.run(verification_router.upload_id_photo(
                front=upload_file(image_bytes()),
                back=upload_file(image_bytes()),
                user=self.user,
                db=self.db,
            ))
            self.assertTrue(result["data"]["front_photo_uploaded"])
            self.assertTrue(result["data"]["back_photo_uploaded"])
            names = sorted(path.name for path in Path(temp_dir).iterdir())
            self.assertEqual(names, [
                f"id_back_{self.user.id}.png",
                f"id_front_{self.user.id}.png",
            ])
            self.assertFalse(any(name.endswith(".tmp") for name in names))

    def test_forged_second_image_rejects_request_before_any_file_is_written(self):
        forged = b"\x89PNG\r\n\x1a\n" + b"not-a-real-image"
        with tempfile.TemporaryDirectory() as temp_dir, patch.object(
            verification_router, "UPLOAD_DIR", Path(temp_dir),
        ):
            with self.assertRaises(BizError):
                asyncio.run(verification_router.upload_id_photo(
                    front=upload_file(image_bytes()),
                    back=upload_file(forged),
                    user=self.user,
                    db=self.db,
                ))
            self.assertEqual(list(Path(temp_dir).iterdir()), [])
            self.db.refresh(self.verification)
            self.assertIsNone(self.verification.front_photo)
            self.assertIsNone(self.verification.back_photo)

    def test_legacy_record_without_consent_cannot_upload_documents(self):
        self.verification.consent_at = None
        self.db.commit()
        with tempfile.TemporaryDirectory() as temp_dir, patch.object(
            verification_router, "UPLOAD_DIR", Path(temp_dir),
        ):
            with self.assertRaisesRegex(BizError, "单独同意") as raised:
                asyncio.run(verification_router.upload_id_photo(
                    front=upload_file(image_bytes()),
                    back=None,
                    user=self.user,
                    db=self.db,
                ))
            self.assertEqual(raised.exception.status_code, 400)
            self.assertEqual(list(Path(temp_dir).iterdir()), [])

    def test_saved_identity_image_is_reencoded_without_exif(self):
        with tempfile.TemporaryDirectory() as temp_dir, patch.object(
            verification_router, "UPLOAD_DIR", Path(temp_dir),
        ):
            asyncio.run(verification_router.upload_id_photo(
                front=upload_file(jpeg_with_exif_bytes()),
                back=None,
                user=self.user,
                db=self.db,
            ))
            saved = Path(temp_dir) / f"id_front_{self.user.id}.jpg"
            with Image.open(saved) as image:
                self.assertIsNone(image.getexif().get(270))

    def test_pixel_limit_is_enforced_before_storage(self):
        with tempfile.TemporaryDirectory() as temp_dir, patch.object(
            verification_router, "UPLOAD_DIR", Path(temp_dir),
        ), patch.object(verification_router.settings, "ID_OCR_MAX_PIXELS", 100):
            with self.assertRaisesRegex(BizError, "像素尺寸过大"):
                asyncio.run(verification_router.upload_id_photo(
                    front=upload_file(image_bytes()),
                    back=None,
                    user=self.user,
                    db=self.db,
                ))
            self.assertEqual(list(Path(temp_dir).iterdir()), [])

    def test_exact_ocr_match_remains_pending_for_manual_approval(self):
        matched = OcrPrecheckResult(
            status="matched",
            summary={
                "name_match": True,
                "id_number_match": True,
                "birth_date_match": True,
                "gender_match": True,
                "validity_match": True,
            },
            valid_from="2020-01-01",
            valid_until="2040-01-01",
        )
        with tempfile.TemporaryDirectory() as temp_dir, patch.object(
            verification_router, "UPLOAD_DIR", Path(temp_dir),
        ), patch.object(
            verification_router.settings, "ID_OCR_ENABLED", True,
        ), patch.object(
            verification_router, "run_identity_precheck", return_value=matched,
        ):
            result = asyncio.run(verification_router.upload_id_photo(
                front=upload_file(image_bytes()),
                back=upload_file(image_bytes()),
                user=self.user,
                db=self.db,
            ))
        self.db.refresh(self.verification)
        self.assertEqual(self.verification.status, "pending")
        self.assertEqual(self.verification.ocr_status, "matched")
        self.assertEqual(result["data"]["status"], "pending")
        self.assertEqual(result["data"]["ocr_status"], "matched")
        self.assertTrue(result["data"]["ocr_summary"]["validity_match"])
        self.assertTrue(self.verification.ocr_summary.startswith("enc:v1:"))
        self.assertNotIn("ocr_input_token", result["data"])

    def test_stale_ocr_result_cannot_overwrite_a_new_photo_generation(self):
        first_token = "a" * 64
        self.verification.ocr_input_token = first_token
        self.verification.ocr_status = "processing"
        self.db.commit()

        verification_router._reset_ocr(self.verification)
        current_token = self.verification.ocr_input_token
        self.db.commit()
        stale_result = OcrPrecheckResult(
            status="matched",
            summary={
                "name_match": True,
                "id_number_match": True,
                "birth_date_match": True,
                "gender_match": True,
                "validity_match": True,
            },
            valid_from="2020-01-01",
            valid_until="2040-01-01",
        )
        stored = verification_router._store_ocr_result_if_current(
            self.db, self.verification.id, first_token, stale_result,
        )

        self.assertFalse(stored)
        self.db.refresh(self.verification)
        self.assertEqual(self.verification.ocr_input_token, current_token)
        self.assertEqual(self.verification.ocr_status, "not_started")
        self.assertIsNone(self.verification.ocr_summary)

    def test_identity_resubmission_rotates_ocr_generation_token(self):
        identity = "11010519491231002X"
        self.verification.real_name = "张三"
        self.verification.id_card = protect(identity)
        self.verification.ocr_input_token = "b" * 64
        self.verification.ocr_status = "matched"
        self.db.commit()

        result = verification_router.submit(
            VerificationIn(
                real_name="张三", id_card=identity, sensitive_consent=True,
            ),
            self.user,
            self.db,
        )

        self.db.refresh(self.verification)
        self.assertNotEqual(self.verification.ocr_input_token, "b" * 64)
        self.assertEqual(self.verification.ocr_status, "not_started")
        self.assertNotIn("ocr_input_token", result["data"])

    def test_router_has_no_public_identity_document_download_route(self):
        paths = {route.path for route in verification_router.router.routes}
        self.assertEqual(paths, {"/api/verification", "/api/verification/upload"})

    def test_changed_identity_clears_and_deletes_both_previous_photos(self):
        identity = "11010519491231002X"
        self.verification.id_card = protect(identity)
        self.verification.front_photo = f"id_front_{self.user.id}.png"
        self.verification.back_photo = f"id_back_{self.user.id}.png"
        self.db.commit()
        with tempfile.TemporaryDirectory() as temp_dir, patch.object(
            verification_router, "UPLOAD_DIR", Path(temp_dir),
        ):
            front = Path(temp_dir) / self.verification.front_photo
            back = Path(temp_dir) / self.verification.back_photo
            front.write_bytes(image_bytes())
            back.write_bytes(image_bytes())
            result = verification_router.submit(
                VerificationIn(
                    real_name="李四", id_card=identity, sensitive_consent=True,
                ),
                self.user,
                self.db,
            )
            self.db.refresh(self.verification)
            self.assertEqual(result["data"]["status"], "pending")
            self.assertIsNone(self.verification.front_photo)
            self.assertIsNone(self.verification.back_photo)
            self.assertFalse(front.exists())
            self.assertFalse(back.exists())
            self.assertIsNotNone(self.verification.consent_at)
            self.assertTrue(result["data"]["consent_recorded"])

    def test_explicit_false_consent_is_rejected_without_writing_a_record(self):
        identity = "11010519491231002X"
        before = self.verification.consent_at
        with self.assertRaisesRegex(BizError, "单独同意") as raised:
            verification_router.submit(
                VerificationIn(
                    real_name="张三", id_card=identity, sensitive_consent=False,
                ),
                self.user,
                self.db,
            )
        self.assertEqual(raised.exception.status_code, 400)
        self.db.refresh(self.verification)
        self.assertEqual(self.verification.consent_at, before)

    def test_missing_consent_from_old_client_returns_explicit_http_400(self):
        request = Request({
            "type": "http",
            "method": "POST",
            "scheme": "http",
            "server": ("testserver", 80),
            "client": ("127.0.0.1", 1234),
            "root_path": "",
            "path": "/api/verification",
            "raw_path": b"/api/verification",
            "query_string": b"",
            "headers": [],
        })
        exc = RequestValidationError([{
            "type": "missing",
            "loc": ("body", "sensitive_consent"),
            "msg": "Field required",
            "input": {"real_name": "张三", "id_card": "masked"},
        }])
        response = asyncio.run(request_validation_handler(request, exc))
        self.assertEqual(response.status_code, 400)
        body = json.loads(response.body)
        self.assertIn("单独同意", body["msg"])


if __name__ == "__main__":
    unittest.main()
