import unittest

from fastapi import HTTPException

from app.core.rate_limit import SlidingWindowRateLimiter, _identity_key


class RateLimitTests(unittest.TestCase):
    def test_account_limit_does_not_merge_different_testers(self):
        limiter = SlidingWindowRateLimiter(limit=2, window_seconds=60)
        limiter.check("login:13900000001")
        limiter.check("login:13900000001")
        with self.assertRaises(HTTPException) as caught:
            limiter.check("login:13900000001")
        self.assertEqual(caught.exception.status_code, 429)

        # A second tester is independently keyed even when both requests
        # arrive from the same nginx/FastAPI socket peer.
        limiter.check("login:13900000002")

    def test_identity_key_is_normalized_and_bounded(self):
        self.assertEqual(_identity_key(" 13900000001 "), "13900000001")
        self.assertEqual(len(_identity_key("X" * 1000)), 128)

    def test_support_limit_is_scoped_by_authenticated_user(self):
        limiter = SlidingWindowRateLimiter(limit=2, window_seconds=60)
        limiter.check("support-message:101")
        limiter.check("support-message:101")
        with self.assertRaises(HTTPException) as caught:
            limiter.check("support-message:101")
        self.assertEqual(caught.exception.status_code, 429)
        limiter.check("support-message:102")

    def test_availability_check_does_not_record_an_event(self):
        limiter = SlidingWindowRateLimiter(limit=2, window_seconds=60)
        limiter.check("register:13900000001")
        limiter.ensure_available("register:13900000001")
        limiter.check("register:13900000001")

        with self.assertRaises(HTTPException) as caught:
            limiter.ensure_available("register:13900000001")

        self.assertEqual(caught.exception.status_code, 429)


if __name__ == "__main__":
    unittest.main()
