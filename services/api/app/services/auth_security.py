from datetime import datetime, timedelta, timezone

from sqlalchemy.orm import Session
from sqlalchemy.exc import IntegrityError

from app.models import AuthRateLimit
from app.security import ApiError, digest


def _aware(value: datetime) -> datetime:
    return value if value.tzinfo else value.replace(tzinfo=timezone.utc)


def client_ip(request) -> str:
    return request.client.host if request.client else "unknown"


def hit_rate_limit(
    db: Session,
    *,
    scope: str,
    identity: str,
    limit: int,
    window_seconds: int,
) -> None:
    now = datetime.now(timezone.utc)
    key_hash = digest(f"auth-rate:{scope}:{identity.strip().casefold()}")
    row = db.query(AuthRateLimit).filter(
        AuthRateLimit.key_hash == key_hash
    ).with_for_update().first()
    if row is None:
        db.add(AuthRateLimit(
            key_hash=key_hash,
            scope=scope,
            attempts=1,
            window_started_at=now,
        ))
        try:
            db.commit()
        except IntegrityError:
            db.rollback()
            hit_rate_limit(
                db,
                scope=scope,
                identity=identity,
                limit=limit,
                window_seconds=window_seconds,
            )
        return
    window_end = _aware(row.window_started_at) + timedelta(seconds=window_seconds)
    if row.blocked_until and _aware(row.blocked_until) > now:
        retry_after = max(1, int((_aware(row.blocked_until) - now).total_seconds()))
        raise ApiError("AUTH_RATE_LIMITED", "尝试次数过多，请稍后再试", 429, {"Retry-After": str(retry_after)})
    if window_end <= now:
        row.attempts = 1
        row.window_started_at = now
        row.blocked_until = None
        db.commit()
        return
    if row.attempts >= limit:
        row.blocked_until = window_end
        db.commit()
        retry_after = max(1, int((window_end - now).total_seconds()))
        raise ApiError("AUTH_RATE_LIMITED", "尝试次数过多，请稍后再试", 429, {"Retry-After": str(retry_after)})
    row.attempts += 1
    db.commit()


def clear_rate_limit(db: Session, *, scope: str, identity: str) -> None:
    key_hash = digest(f"auth-rate:{scope}:{identity.strip().casefold()}")
    db.query(AuthRateLimit).filter(AuthRateLimit.key_hash == key_hash).delete()
    db.commit()
