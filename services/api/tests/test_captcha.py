import base64
import io
import time
import unittest
from concurrent.futures import ThreadPoolExecutor
from threading import Barrier, Lock
from unittest.mock import patch

from PIL import Image

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

        self.assertTrue(captcha.verify_captcha(challenge["key"], "a2bc"))
        self.assertFalse(captcha.verify_captcha(challenge["key"], "A2BC"))

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

    def test_wrong_code_does_not_consume_captcha(self):
        key = "retry-key"
        captcha.CAPTCHA_STORE[key] = {
            "code": "B3CD",
            "expire": time.time() + 60,
        }

        self.assertFalse(captcha.verify_captcha(key, "WRONG"))
        self.assertTrue(captcha.verify_captcha(key, " b3cd "))
        self.assertNotIn(key, captcha.CAPTCHA_STORE)

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
