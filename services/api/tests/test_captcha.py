import base64
import io
import time
import unittest
from concurrent.futures import ThreadPoolExecutor
from threading import Barrier, Lock
from unittest.mock import patch

from fastapi import FastAPI
from fastapi.exceptions import RequestValidationError
from fastapi.testclient import TestClient
from PIL import Image

from app.core.rate_limit import limit_captcha
from app.main import request_validation_handler
from app.routers.auth import router as auth_router
from app.utils import captcha


class _BarrierLock:
    """让并发验证同时到达互斥锁，避免测试依赖线程调度概率。"""

    def __init__(self, parties: int):
        self._barrier = Barrier(parties)
        self._lock = Lock()
        self.entries = 0

    def __enter__(self):
        self.entries += 1
        self._barrier.wait(timeout=5)
        self._lock.acquire()
        return self

    def __exit__(self, exc_type, exc_value, traceback):
        self._lock.release()


class CaptchaTests(unittest.TestCase):
    def setUp(self):
        captcha.CAPTCHA_STORE.clear()

    def tearDown(self):
        captcha.CAPTCHA_STORE.clear()

    def test_created_challenge_is_a_raster_png_without_text_markup_or_metadata(self):
        with patch.object(captcha, "_generate_code", return_value="A2BC"):
            challenge = captcha.create_captcha()

        self.assertRegex(challenge["key"], r"^[0-9a-f]{24}$")
        self.assertTrue(challenge["image"].startswith("data:image/png;base64,"))
        payload = base64.b64decode(challenge["image"].split(",", 1)[1], validate=True)
        self.assertTrue(payload.startswith(b"\x89PNG\r\n\x1a\n"))
        self.assertNotIn(b"<svg", payload.lower())
        self.assertNotIn(b"<text", payload.lower())

        with Image.open(io.BytesIO(payload)) as rendered:
            self.assertEqual(rendered.format, "PNG")
            self.assertEqual(rendered.size, (120, 50))
            self.assertEqual(rendered.mode, "RGB")
            self.assertFalse(rendered.info)
            self.assertFalse(rendered.text)

        self.assertEqual(captcha.CAPTCHA_STORE[challenge["key"]]["failures"], 0)
        self.assertTrue(captcha.verify_captcha(challenge["key"], "a2bc"))
        self.assertFalse(captcha.verify_captcha(challenge["key"], "A2BC"))

    def test_endpoint_prevents_clients_and_proxies_from_caching_a_challenge(self):
        api = FastAPI()
        api.include_router(auth_router)
        api.dependency_overrides[limit_captcha] = lambda: None

        with TestClient(api) as client:
            response = client.get("/api/auth/captcha")

        self.assertEqual(response.status_code, 200)
        self.assertIn("no-store", response.headers["cache-control"])
        self.assertIn("no-cache", response.headers["cache-control"])
        self.assertEqual(response.headers["pragma"], "no-cache")
        self.assertEqual(response.headers["expires"], "0")
        self.assertTrue(response.json()["data"]["image"].startswith("data:image/png;base64,"))

    def test_code_uses_only_unambiguous_characters(self):
        for length in (1, 4, 6):
            code = captcha._generate_code(length)
            self.assertEqual(len(code), length)
            self.assertTrue(set(code) <= set(captcha._CAPTCHA_CHARS))

    def test_code_uses_cryptographically_secure_choice(self):
        with patch.object(captcha.secrets, "choice", side_effect=list("A2BC")) as secure_choice:
            self.assertEqual(captcha._generate_code(), "A2BC")
        self.assertEqual(secure_choice.call_count, 4)

    def test_rotated_edge_characters_are_fitted_inside_the_canvas(self):
        layer = Image.new("RGBA", (50, 50), (0, 0, 0, 0))
        layer.paste((10, 20, 30, 255), (4, 5, 48, 46))

        self.assertEqual(captcha._fit_layer_position(-20, -20, layer, (120, 50)), (-4, -5))
        self.assertEqual(captcha._fit_layer_position(110, 20, layer, (120, 50)), (72, 4))

    def test_correct_code_is_consumed_exactly_once_under_concurrency(self):
        key = "concurrent-key"
        captcha.CAPTCHA_STORE[key] = {
            "code": "A2BC",
            "expire": time.time() + 60,
        }
        barrier_lock = _BarrierLock(parties=2)

        with patch.object(captcha, "_CAPTCHA_LOCK", barrier_lock):
            with ThreadPoolExecutor(max_workers=2) as executor:
                results = list(executor.map(lambda _: captcha.verify_captcha(key, "a2bc"), range(2)))

        self.assertEqual(results.count(True), 1)
        self.assertEqual(results.count(False), 1)
        self.assertEqual(barrier_lock.entries, 2)
        self.assertNotIn(key, captcha.CAPTCHA_STORE)

    def test_wrong_codes_allow_a_correct_retry_before_the_limit(self):
        key = "retry-key"
        captcha.CAPTCHA_STORE[key] = {
            "code": "B3CD",
            "expire": time.time() + 60,
        }

        for _ in range(captcha.CAPTCHA_MAX_FAILURES - 1):
            self.assertFalse(captcha.verify_captcha(key, "WRONG"))

        self.assertEqual(
            captcha.CAPTCHA_STORE[key]["failures"],
            captcha.CAPTCHA_MAX_FAILURES - 1,
        )
        self.assertTrue(captcha.verify_captcha(key, " b3cd "))
        self.assertNotIn(key, captcha.CAPTCHA_STORE)

    def test_too_many_wrong_codes_invalidate_the_captcha(self):
        key = "guess-limited-key"
        captcha.CAPTCHA_STORE[key] = {
            "code": "D5EF",
            "expire": time.time() + 60,
        }

        for _ in range(captcha.CAPTCHA_MAX_FAILURES):
            self.assertFalse(captcha.verify_captcha(key, "WRONG"))

        self.assertNotIn(key, captcha.CAPTCHA_STORE)
        self.assertFalse(captcha.verify_captcha(key, "D5EF"))

    def test_wrong_attempt_limit_is_atomic_under_concurrency(self):
        key = "concurrent-guess-key"
        captcha.CAPTCHA_STORE[key] = {
            "code": "E6FG",
            "expire": time.time() + 60,
            "failures": 0,
        }
        attempts = captcha.CAPTCHA_MAX_FAILURES + 3
        barrier_lock = _BarrierLock(parties=attempts)

        with patch.object(captcha, "_CAPTCHA_LOCK", barrier_lock):
            with ThreadPoolExecutor(max_workers=attempts) as executor:
                results = list(executor.map(
                    lambda _: captcha.verify_captcha(key, "WRONG"),
                    range(attempts),
                ))

        self.assertEqual(results, [False] * attempts)
        self.assertEqual(barrier_lock.entries, attempts)
        self.assertNotIn(key, captcha.CAPTCHA_STORE)
        self.assertFalse(captcha.verify_captcha(key, "E6FG"))

    def test_oversized_inputs_are_rejected_without_consuming_a_challenge(self):
        key = "f" * 24
        captcha.CAPTCHA_STORE[key] = {
            "code": "F7GH",
            "expire": time.time() + 60,
            "failures": 0,
        }

        self.assertFalse(captcha.verify_captcha(
            key,
            "X" * (captcha.CAPTCHA_CODE_INPUT_MAX_LENGTH + 1),
        ))
        self.assertFalse(captcha.verify_captcha(
            "f" * (captcha.CAPTCHA_KEY_INPUT_MAX_LENGTH + 1),
            "F7GH",
        ))
        self.assertEqual(captcha.CAPTCHA_STORE[key]["failures"], 0)
        self.assertTrue(captcha.verify_captcha(key, "F7GH"))

    def test_registration_validation_never_reflects_rejected_inputs(self):
        api = FastAPI()
        api.add_exception_handler(RequestValidationError, request_validation_handler)
        api.include_router(auth_router)
        private_password = "private-password-marker"
        oversized_key = "key-marker-" + "a" * captcha.CAPTCHA_KEY_INPUT_MAX_LENGTH
        oversized_code = "CODE123"

        with patch("app.routers.auth.verify_captcha") as verify:
            with TestClient(api) as client:
                response = client.post("/api/auth/register", json={
                    "phone": "13900000062",
                    "password": private_password,
                    "captcha_key": oversized_key,
                    "captcha_code": oversized_code,
                })

        self.assertEqual(response.status_code, 422)
        self.assertTrue(all("input" not in item for item in response.json()["detail"]))
        self.assertNotIn(private_password, response.text)
        self.assertNotIn(oversized_key, response.text)
        self.assertNotIn(oversized_code, response.text)
        verify.assert_not_called()

    def test_expired_captcha_is_removed(self):
        key = "expired-key"
        captcha.CAPTCHA_STORE[key] = {
            "code": "C4DE",
            "expire": time.time() - 1,
        }

        self.assertFalse(captcha.verify_captcha(key, "C4DE"))
        self.assertNotIn(key, captcha.CAPTCHA_STORE)


if __name__ == "__main__":
    unittest.main()
