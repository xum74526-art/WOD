from __future__ import annotations

from collections import defaultdict, deque
import hashlib
from threading import Lock
from time import monotonic

from fastapi import HTTPException, status

from app.core.sensitive import fingerprint


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

    def ensure_available(self, key: str) -> None:
        """Reject a full bucket without recording a new event."""
        now = monotonic()
        cutoff = now - self.window_seconds
        with self._lock:
            events = self._events.get(key)
            if not events:
                return
            while events and events[0] <= cutoff:
                events.popleft()
            if not events:
                self._events.pop(key, None)
                return
            if len(events) >= self.limit:
                raise HTTPException(
                    status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                    detail="请求过于频繁，请稍后再试",
                    headers={"Retry-After": str(self.window_seconds)},
                )


captcha_global_rate_limit = SlidingWindowRateLimiter(limit=600, window_seconds=60)
register_global_rate_limit = SlidingWindowRateLimiter(limit=300, window_seconds=600)
register_account_rate_limit = SlidingWindowRateLimiter(limit=5, window_seconds=600)
login_global_rate_limit = SlidingWindowRateLimiter(limit=1200, window_seconds=60)
login_account_rate_limit = SlidingWindowRateLimiter(limit=10, window_seconds=60)
support_message_rate_limit = SlidingWindowRateLimiter(limit=20, window_seconds=60)
support_ticket_rate_limit = SlidingWindowRateLimiter(limit=5, window_seconds=3600)
recovery_request_global_rate_limit = SlidingWindowRateLimiter(limit=300, window_seconds=600)
recovery_request_account_rate_limit = SlidingWindowRateLimiter(limit=5, window_seconds=600)
recovery_confirm_global_rate_limit = SlidingWindowRateLimiter(limit=600, window_seconds=60)
recovery_confirm_token_rate_limit = SlidingWindowRateLimiter(limit=10, window_seconds=600)
recovery_binding_rate_limit = SlidingWindowRateLimiter(limit=5, window_seconds=600)
phone_login_setup_rate_limit = SlidingWindowRateLimiter(limit=5, window_seconds=600)
payment_create_rate_limit = SlidingWindowRateLimiter(limit=10, window_seconds=60)
payment_query_rate_limit = SlidingWindowRateLimiter(limit=30, window_seconds=60)
payment_checkout_rate_limit = SlidingWindowRateLimiter(limit=20, window_seconds=60)
payment_callback_rate_limit = SlidingWindowRateLimiter(limit=3000, window_seconds=60)
payment_admin_rate_limit = SlidingWindowRateLimiter(limit=30, window_seconds=60)
payment_refund_request_rate_limit = SlidingWindowRateLimiter(limit=5, window_seconds=3600)
notification_broadcast_rate_limit = SlidingWindowRateLimiter(limit=10, window_seconds=3600)
admin_account_action_rate_limit = SlidingWindowRateLimiter(limit=60, window_seconds=60)
admin_onboarding_action_rate_limit = SlidingWindowRateLimiter(limit=120, window_seconds=60)
coupon_redeem_rate_limit = SlidingWindowRateLimiter(limit=10, window_seconds=600)
admin_coupon_action_rate_limit = SlidingWindowRateLimiter(limit=60, window_seconds=60)


def _identity_key(value: str) -> str:
    # The Pydantic schema still performs the actual format validation. This
    # bounded normalization only prevents attacker-controlled unbounded keys.
    return (value or "<empty>").strip().lower()[:128]


def limit_captcha() -> None:
    # ELB -> nginx -> FastAPI means request.client is normally 127.0.0.1.
    # A deliberately wide endpoint guard avoids treating all testers as one
    # person while still containing accidental request storms.
    captcha_global_rate_limit.check("captcha:global")


def limit_register_request() -> None:
    register_global_rate_limit.check("register:global")


def ensure_register_account_available(identity: str) -> None:
    register_account_rate_limit.ensure_available(f"register:{_identity_key(identity)}")


def limit_register_account(identity: str) -> None:
    register_account_rate_limit.check(f"register:{_identity_key(identity)}")


def limit_register(identity: str) -> None:
    """Compatibility wrapper for callers that need both registration guards."""
    limit_register_request()
    limit_register_account(identity)


def limit_login(identity: str) -> None:
    login_global_rate_limit.check("login:global")
    login_account_rate_limit.check(f"login:{_identity_key(identity)}")


def limit_support_message(user_id: int) -> None:
    support_message_rate_limit.check(f"support-message:{int(user_id)}")


def limit_support_ticket(user_id: int) -> None:
    support_ticket_rate_limit.check(f"support-ticket:{int(user_id)}")


def limit_password_reset_request(email: str) -> None:
    recovery_request_global_rate_limit.check("recovery-request:global")
    # Do not retain plaintext recovery addresses in the process-local limiter.
    recovery_request_account_rate_limit.check(
        f"recovery-request:{fingerprint(_identity_key(email))}"
    )


def limit_recovery_confirm(token: str) -> None:
    recovery_confirm_global_rate_limit.check("recovery-confirm:global")
    digest = hashlib.sha256(str(token or "").encode("utf-8")).hexdigest()
    recovery_confirm_token_rate_limit.check(f"recovery-confirm:{digest}")


def limit_recovery_email_binding(user_id: int) -> None:
    recovery_binding_rate_limit.check(f"recovery-binding:{int(user_id)}")


def limit_phone_login_setup(user_id: int) -> None:
    phone_login_setup_rate_limit.check(f"phone-login-setup:{int(user_id)}")


def limit_payment_create(user_id: int) -> None:
    payment_create_rate_limit.check(f"payment-create:{int(user_id)}")


def limit_payment_query(user_id: int) -> None:
    payment_query_rate_limit.check(f"payment-query:{int(user_id)}")


def limit_payment_checkout(token: str) -> None:
    digest = hashlib.sha256(str(token or "").encode("utf-8")).hexdigest()
    payment_checkout_rate_limit.check(f"payment-checkout:{digest}")


def limit_payment_callback(provider: str) -> None:
    payment_callback_rate_limit.check(f"payment-callback:{provider[:24]}")


def limit_payment_admin(user_id: int) -> None:
    payment_admin_rate_limit.check(f"payment-admin:{int(user_id)}")


def limit_payment_refund_request(user_id: int) -> None:
    payment_refund_request_rate_limit.check(f"payment-refund-request:{int(user_id)}")


def limit_notification_broadcast(user_id: int) -> None:
    """Bound accidental/replayed all-user announcements per administrator."""

    notification_broadcast_rate_limit.check(f"notification-broadcast:{int(user_id)}")


def limit_admin_account_action(user_id: int) -> None:
    """Contain accidental bulk account mutations from one admin session."""

    admin_account_action_rate_limit.check(f"admin-account-action:{int(user_id)}")


def limit_admin_onboarding_action(user_id: int) -> None:
    """Bound hosting-review writes without consuming the account-action bucket."""

    admin_onboarding_action_rate_limit.check(f"admin-onboarding-action:{int(user_id)}")


def limit_coupon_redeem(user_id: int) -> None:
    """Slow online guessing without exposing redemption codes in limiter keys."""

    coupon_redeem_rate_limit.check(f"coupon-redeem:{int(user_id)}")


def limit_admin_coupon_action(user_id: int) -> None:
    """Contain accidental campaign creation or repeated status changes."""

    admin_coupon_action_rate_limit.check(f"admin-coupon-action:{int(user_id)}")
