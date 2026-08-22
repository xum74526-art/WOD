from __future__ import annotations

from collections import defaultdict, deque
from threading import Lock
from time import monotonic

from fastapi import HTTPException, status


class SlidingWindowRateLimiter:
    """Small single-process limiter keyed by a server-controlled identifier."""

    def __init__(self, limit: int, window_seconds: int):
        self.limit = limit
        self.window_seconds = window_seconds
        self._events: dict[str, deque[float]] = defaultdict(deque)
        self._lock = Lock()

    def check(self, key: str) -> None:
        now = monotonic()
        cutoff = now - self.window_seconds
        with self._lock:
            events = self._events[key]
            while events and events[0] <= cutoff:
                events.popleft()
            if len(events) >= self.limit:
                raise HTTPException(
                    status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                    detail="请求过于频繁，请稍后再试",
                    headers={"Retry-After": str(self.window_seconds)},
                )
            events.append(now)
            # Avoid retaining idle keys indefinitely on a long-running worker.
            if len(self._events) > 10000:
                for stale_key in list(self._events)[:1000]:
                    if not self._events[stale_key] or self._events[stale_key][-1] <= cutoff:
                        self._events.pop(stale_key, None)


captcha_global_rate_limit = SlidingWindowRateLimiter(limit=600, window_seconds=60)
register_global_rate_limit = SlidingWindowRateLimiter(limit=300, window_seconds=600)
register_account_rate_limit = SlidingWindowRateLimiter(limit=5, window_seconds=600)
login_global_rate_limit = SlidingWindowRateLimiter(limit=1200, window_seconds=60)
login_account_rate_limit = SlidingWindowRateLimiter(limit=10, window_seconds=60)
support_message_rate_limit = SlidingWindowRateLimiter(limit=20, window_seconds=60)
support_ticket_rate_limit = SlidingWindowRateLimiter(limit=5, window_seconds=3600)


def _identity_key(value: str) -> str:
    # The Pydantic schema still performs the actual format validation. This
    # bounded normalization only prevents attacker-controlled unbounded keys.
    return (value or "<empty>").strip().lower()[:128]


def limit_captcha() -> None:
    # ELB -> nginx -> FastAPI means request.client is normally 127.0.0.1.
    # A deliberately wide endpoint guard avoids treating all testers as one
    # person while still containing accidental request storms.
    captcha_global_rate_limit.check("captcha:global")


def limit_register(identity: str) -> None:
    register_global_rate_limit.check("register:global")
    register_account_rate_limit.check(f"register:{_identity_key(identity)}")


def limit_login(identity: str) -> None:
    login_global_rate_limit.check("login:global")
    login_account_rate_limit.check(f"login:{_identity_key(identity)}")


def limit_support_message(user_id: int) -> None:
    support_message_rate_limit.check(f"support-message:{int(user_id)}")


def limit_support_ticket(user_id: int) -> None:
    support_ticket_rate_limit.check(f"support-ticket:{int(user_id)}")
