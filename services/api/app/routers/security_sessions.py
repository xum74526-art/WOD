from datetime import datetime, timezone

from fastapi import APIRouter, Depends, Header, Request, Response
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session

from app.config import settings
from app.db import get_db
from app.models import Session as LoginSession
from app.models import User
from app.responses import ok
from app.schemas import PasswordChangeIn
from app.security import (
    CSRF_COOKIE,
    SESSION_COOKIE,
    ApiError,
    current_bearer_session,
    current_session,
    get_current_user,
    hash_password,
    require_csrf,
    require_authenticated_action,
    verify_password,
)


router = APIRouter(prefix="/api/v1/account/security", tags=["account-security"])


def _aware(value: datetime) -> datetime:
    return value if value.tzinfo else value.replace(tzinfo=timezone.utc)


def _session_out(row: LoginSession, current_id: str, now: datetime) -> dict:
    status = "revoked" if row.revoked_at else "expired" if _aware(row.expires_at) <= now else "active"
    return {
        "id": row.id,
        "channel": row.channel,
        "device_name": row.device_name,
        "ip_address": row.ip_address_masked,
        "status": status,
        "is_current": row.id == current_id,
        "created_at": row.created_at,
        "last_seen_at": row.last_seen_at,
        "expires_at": row.expires_at,
        "revoked_at": row.revoked_at,
        "revoke_reason": row.revoke_reason,
    }


def _clear_session_cookies(response: JSONResponse) -> None:
    response.delete_cookie(SESSION_COOKIE, path="/")
    response.delete_cookie(CSRF_COOKIE, path="/")


@router.get("/sessions")
def list_sessions(
    request: Request,
    response: Response,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    response.headers["Cache-Control"] = "no-store"
    current = current_session(request, db)
    now = datetime.now(timezone.utc)
    rows = db.query(LoginSession).filter(
        LoginSession.user_id == user.id
    ).order_by(LoginSession.last_seen_at.desc(), LoginSession.created_at.desc()).limit(100).all()
    return ok({
        "account": {
            "display_name": user.display_name,
            "email": user.email,
            "email_verified": user.email_verified,
            "role": user.role,
        },
        "sessions": [_session_out(row, current.id, now) for row in rows],
        "session_ttl_days": settings.SESSION_TTL_DAYS,
    })


@router.post("/sessions/{session_id}/revoke")
def revoke_session(
    session_id: str,
    request: Request,
    user: User = Depends(require_csrf),
    db: Session = Depends(get_db),
):
    current = current_session(request, db)
    target = db.query(LoginSession).filter(
        LoginSession.id == session_id,
        LoginSession.user_id == user.id,
    ).with_for_update().first()
    if target is None:
        raise ApiError("SESSION_NOT_FOUND", "登录设备不存在", 404)
    if target.revoked_at is None:
        target.revoked_at = datetime.now(timezone.utc)
        target.revoke_reason = "user_device_revoke"
        db.commit()
    result = JSONResponse(ok({"revoked": True, "current_session_revoked": target.id == current.id}))
    result.headers["Cache-Control"] = "no-store"
    if target.id == current.id:
        _clear_session_cookies(result)
    return result


@router.post("/sessions/revoke-others")
def revoke_other_sessions(
    request: Request,
    user: User = Depends(require_csrf),
    db: Session = Depends(get_db),
):
    current = current_session(request, db)
    now = datetime.now(timezone.utc)
    count = db.query(LoginSession).filter(
        LoginSession.user_id == user.id,
        LoginSession.id != current.id,
        LoginSession.revoked_at.is_(None),
    ).update({LoginSession.revoked_at: now, LoginSession.revoke_reason: "user_revoke_others"}, synchronize_session=False)
    db.commit()
    return JSONResponse(ok({"revoked_count": count}), headers={"Cache-Control": "no-store"})


@router.post("/sessions/revoke-all")
def revoke_all_sessions(
    request: Request,
    user: User = Depends(require_csrf),
    db: Session = Depends(get_db),
):
    current_session(request, db)
    now = datetime.now(timezone.utc)
    count = db.query(LoginSession).filter(
        LoginSession.user_id == user.id,
        LoginSession.revoked_at.is_(None),
    ).update({LoginSession.revoked_at: now, LoginSession.revoke_reason: "user_revoke_all"}, synchronize_session=False)
    db.commit()
    result = JSONResponse(ok({"revoked_count": count}), headers={"Cache-Control": "no-store"})
    _clear_session_cookies(result)
    return result


@router.post("/password")
def change_password(
    data: PasswordChangeIn,
    request: Request,
    authorization: str | None = Header(default=None),
    user: User = Depends(require_authenticated_action),
    db: Session = Depends(get_db),
):
    current = current_bearer_session(authorization, db) if authorization else current_session(request, db)
    if not verify_password(data.current_password, user.password_hash):
        raise ApiError("CURRENT_PASSWORD_INVALID", "当前密码不正确", 400)
    if verify_password(data.new_password, user.password_hash):
        raise ApiError("PASSWORD_REUSE_FORBIDDEN", "新密码不能与当前密码相同", 409)
    now = datetime.now(timezone.utc)
    user.password_hash = hash_password(data.new_password)
    revoked_count = db.query(LoginSession).filter(
        LoginSession.user_id == user.id,
        LoginSession.id != current.id,
        LoginSession.revoked_at.is_(None),
    ).update({LoginSession.revoked_at: now, LoginSession.revoke_reason: "password_change"}, synchronize_session=False)
    db.commit()
    return JSONResponse(ok({"changed": True, "revoked_other_sessions": revoked_count}), headers={"Cache-Control": "no-store"})
