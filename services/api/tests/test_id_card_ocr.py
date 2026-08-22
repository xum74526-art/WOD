import subprocess
import unittest
from datetime import date
from pathlib import Path
from unittest.mock import Mock, patch

from sqlalchemy import create_engine, inspect, text

import init_db
from app.services import id_card_ocr


FRONT_TEXT = """
姓名 张三
性别 女 民族 汉
出生 1949年12月31日
公民身份号码 11010519491231002X
"""

BACK_TEXT = """
中华人民共和国
居民身份证
签发机关 北京市公安局
有效期限 2020.01.01-2040.01.01
"""


class IdCardOcrTests(unittest.TestCase):
    def test_parser_extracts_front_and_back_without_raw_data_correction(self):
        front = id_card_ocr.parse_front(FRONT_TEXT)
        back = id_card_ocr.parse_back(BACK_TEXT)
        self.assertEqual(front.name, "张三")
        self.assertEqual(front.gender, "女")
        self.assertEqual(front.birth_date, "1949-12-31")
        self.assertEqual(front.id_number, "11010519491231002X")
        self.assertEqual(back.valid_from, "2020-01-01")
        self.assertEqual(back.valid_until, "2040-01-01")
        self.assertFalse(back.long_term)

    def test_all_exact_matches_produce_matched_precheck_only(self):
        with patch.object(id_card_ocr.settings, "ID_OCR_ENABLED", True), patch.object(
            id_card_ocr, "_run_tesseract", side_effect=[FRONT_TEXT, BACK_TEXT],
        ):
            result = id_card_ocr.run_identity_precheck(
                Path("front.png"),
                Path("back.png"),
                real_name="张三",
                id_number="11010519491231002X",
                today=date(2026, 8, 20),
            )
        self.assertEqual(result.status, "matched")
        self.assertTrue(all(result.summary.values()))
        self.assertIsNone(result.error_code)

    def test_mismatch_requires_review_and_does_not_guess_ocr_typos(self):
        with patch.object(id_card_ocr.settings, "ID_OCR_ENABLED", True), patch.object(
            id_card_ocr, "_run_tesseract", side_effect=[FRONT_TEXT.replace("张三", "李四"), BACK_TEXT],
        ):
            result = id_card_ocr.run_identity_precheck(
                Path("front.png"),
                Path("back.png"),
                real_name="张三",
                id_number="11010519491231002X",
                today=date(2026, 8, 20),
            )
        self.assertEqual(result.status, "review_required")
        self.assertFalse(result.summary["name_match"])
        self.assertTrue(result.summary["id_number_match"])
        self.assertEqual(result.error_code, "document_data_mismatch")

    def test_expired_validity_never_matches(self):
        expired = BACK_TEXT.replace("2040.01.01", "2021.01.01")
        with patch.object(id_card_ocr.settings, "ID_OCR_ENABLED", True), patch.object(
            id_card_ocr, "_run_tesseract", side_effect=[FRONT_TEXT, expired],
        ):
            result = id_card_ocr.run_identity_precheck(
                Path("front.png"), Path("back.png"),
                real_name="张三", id_number="11010519491231002X",
                today=date(2026, 8, 20),
            )
        self.assertFalse(result.summary["validity_match"])
        self.assertEqual(result.status, "review_required")

    def test_tesseract_is_invoked_with_argument_list_and_no_shell(self):
        completed = Mock(returncode=0, stdout=FRONT_TEXT, stderr="")
        with patch.object(id_card_ocr.settings, "ID_OCR_TESSERACT_CMD", "tesseract"), patch(
            "app.services.id_card_ocr.subprocess.run", return_value=completed,
        ) as run:
            output = id_card_ocr._run_tesseract(Path("safe.png"))
        self.assertIn("姓名", output)
        args, kwargs = run.call_args
        self.assertIsInstance(args[0], list)
        self.assertFalse(kwargs["shell"])
        self.assertEqual(kwargs["stdin"], subprocess.DEVNULL)

    def test_disabled_engine_is_explicitly_unavailable(self):
        with patch.object(id_card_ocr.settings, "ID_OCR_ENABLED", False):
            result = id_card_ocr.run_identity_precheck(
                Path("front.png"), Path("back.png"),
                real_name="张三", id_number="11010519491231002X",
            )
        self.assertEqual(result.status, "unavailable")
        self.assertEqual(result.error_code, "disabled")
        self.assertIsNone(result.summary)

    def test_legacy_schema_migration_is_idempotent(self):
        engine = create_engine("sqlite://")
        with engine.begin() as connection:
            connection.execute(text(
                "CREATE TABLE verifications ("
                "id INTEGER PRIMARY KEY, user_id INTEGER, status TEXT)"
            ))
            connection.execute(text(
                "INSERT INTO verifications (id, user_id, status) VALUES (1, 7, 'pending')"
            ))
        init_db._ensure_columns(engine)
        init_db._ensure_columns(engine)
        columns = {column["name"] for column in inspect(engine).get_columns("verifications")}
        self.assertTrue({
            "ocr_status", "ocr_summary", "ocr_error_code", "ocr_updated_at",
            "ocr_input_token", "consent_at",
        }.issubset(columns))
        with engine.connect() as connection:
            status = connection.execute(text(
                "SELECT ocr_status FROM verifications WHERE id = 1"
            )).scalar_one()
        self.assertEqual(status, "not_started")


if __name__ == "__main__":
    unittest.main()
