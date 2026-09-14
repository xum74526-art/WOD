import time
import unittest
from concurrent.futures import ThreadPoolExecutor
from threading import Barrier, Lock
from unittest.mock import patch

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
