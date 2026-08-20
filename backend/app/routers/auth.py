import secrets
from datetime import datetime, timedelta, timezone
from urllib.parse import quote

from fastapi import APIRouter, Depends, Request
from fastapi.responses import JSONResponse, RedirectResponse
from sqlalchemy.orm import Session

from app.config import settings
from app.db import get_db
from app import email_delivery
from app.models import EmailVerificationToken, PasswordResetToken
from app.models import Session as LoginSession
from app.models import User
from app.responses import ok
from app.schemas import (
    CodeRequestIn,
    EmailLoginIn,
    EmailRegisterIn,
    EmailVerificationConfirmIn,
    PasswordResetConfirmIn,
    PasswordResetRequestIn,
    PhoneAuthIn,
)
from app.security import (
    CSRF_COOKIE,
    SESSION_COOKIE,
    ApiError,
    create_session,
    current_session,
    digest,
    get_current_user,
    hash_password,
    require_csrf,
    verify_password,
)
from app.services.auth_security import client_ip, clear_rate_limit, hit_rate_limit

router = APIRouter(prefix="/api/v1/auth", tags=["auth"])


def _issue_email_verification(db: Session, user: User) -> None:
    if not email_delivery.email_configured():
        raise ApiError("EMAIL_PROVIDER_UNCONFIGURED", "邮箱验证服务尚未配置", 503)
    now = datetime.now(timezone.utc)
    db.query(EmailVerificationToken).filter(
        EmailVerificationToken.user_id == user.id,
        EmailVerificationToken.used_at.is_(None),
    ).update({EmailVerificationToken.used_at: now}, synchronize_session=False)
    raw_token = secrets.token_urlsafe(48)
    db.add(EmailVerificationToken(
        user_id=user.id,
        token_hash=digest(raw_token),
        expires_at=now + timedelta(hours=settings.EMAIL_VERIFICATION_TTL_HOURS),
    ))
    verification_url = f"{settings.FRONTEND_BASE_URL.rstrip('/')}/verify-email?token={quote(raw_token)}"
    try:
        email_delivery.send_verification_email(user.email, verification_url)
    except email_delivery.EmailDeliveryError as exc:
        db.rollback()
        raise ApiError("EMAIL_DELIVERY_FAILED", "验证邮件暂时无法发送", 503) from exc


def _user_out(user: User) -> dict:
    return {
        "id": user.id,
        "display_name": user.display_name,
        "email": user.email,
        "email_verified": user.email_verified,
        "phone": user.phone,
        "phone_verified": user.phone_verified,
        "role": user.role,
    }


def _session_response(user: User, db: Session, request: Request, status_code: int = 200) -> JSONResponse:
    session_token, csrf_token = create_session(user, db, request)
    response = JSONResponse(ok({"user": _user_out(user)}), status_code=status_code)
    response.headers["Cache-Control"] = "no-store"
    max_age = settings.SESSION_TTL_DAYS * 24 * 60 * 60
    response.set_cookie(
        SESSION_COOKIE,
        session_token,
        max_age=max_age,
        httponly=True,
        secure=settings.COOKIE_SECURE,
        samesite="lax",
        path="/",
    )
    response.set_cookie(
        CSRF_COOKIE,
        csrf_token,
        max_age=max_age,
        httponly=False,
        secure=settings.COOKIE_SECURE,
        samesite="lax",
        path="/",
    )
    return response


@router.post("/email/register")
def email_register(data: EmailRegisterIn, request: Request, db: Session = Depends(get_db)):
    hit_rate_limit(db, scope="register_ip", identity=client_ip(request), limit=100, window_seconds=3600)
    email = str(data.email).strip().lower()
    if db.query(User).filter(User.email == email).first():
        raise ApiError("EMAIL_EXISTS", "该邮箱已注册", 409)
    user = User(
        display_name=data.name.strip(),
        email=email,
        email_verified=False,
        password_hash=hash_password(data.password),
        role="personal",
        status="active",
    )
    db.add(user)
    db.flush()
    if settings.EMAIL_VERIFICATION_ENABLED:
        _issue_email_verification(db, user)
    db.commit()
    db.refresh(user)
    return _session_response(user, db, request, status_code=201)


@router.post("/email/login")
def email_login(data: EmailLoginIn, request: Request, db: Session = Depends(get_db)):
    email = str(data.email).strip().lower()
    hit_rate_limit(db, scope="login_ip", identity=client_ip(request), limit=60, window_seconds=900)
    user = db.query(User).filter(User.email == email).first()
    if not user or not verify_password(data.password, user.password_hash):
        hit_rate_limit(db, scope="login_account_failure", identity=email, limit=5, window_seconds=900)
        raise ApiError("INVALID_CREDENTIALS", "邮箱或密码不正确", 401)
    if user.status != "active":
        raise ApiError("ACCOUNT_UNAVAILABLE", "账户不可用", 403)
    clear_rate_limit(db, scope="login_account_failure", identity=email)
    return _session_response(user, db, request)


@router.post("/email/password-reset/request", status_code=202)
def request_password_reset(
    data: PasswordResetRequestIn,
    request: Request,
    db: Session = Depends(get_db),
):
    if not email_delivery.password_reset_email_configured():
        raise ApiError("EMAIL_PROVIDER_UNCONFIGURED", "密码重置邮件服务尚未配置", 503)
    email = str(data.email).strip().lower()
    hit_rate_limit(db, scope="password_reset_ip", identity=client_ip(request), limit=20, window_seconds=3600)
    hit_rate_limit(db, scope="password_reset_email", identity=email, limit=3, window_seconds=3600)
    user = db.query(User).filter(User.email == email, User.status == "active").first()
    if user is not None:
        now = datetime.now(timezone.utc)
        db.query(PasswordResetToken).filter(
            PasswordResetToken.user_id == user.id,
            PasswordResetToken.used_at.is_(None),
        ).update({PasswordResetToken.used_at: now}, synchronize_session=False)
        raw_token = secrets.token_urlsafe(48)
        token = PasswordResetToken(
            user_id=user.id,
            token_hash=digest(raw_token),
            expires_at=now + timedelta(minutes=settings.PASSWORD_RESET_TTL_MINUTES),
        )
        db.add(token)
        db.commit()
        reset_url = f"{settings.FRONTEND_BASE_URL.rstrip('/')}/reset-password?token={quote(raw_token)}"
        try:
            email_delivery.send_password_reset_email(email, reset_url)
        except email_delivery.EmailDeliveryError as exc:
            token.used_at = datetime.now(timezone.utc)
            db.commit()
            raise ApiError("EMAIL_DELIVERY_FAILED", "密码重置邮件暂时无法发送", 503) from exc
    response = JSONResponse(ok({"accepted": True}), status_code=202)
    response.headers["Cache-Control"] = "no-store"
    return response


@router.post("/email/verification/resend", status_code=202)
def resend_email_verification(
    user: User = Depends(require_csrf),
    db: Session = Depends(get_db),
):
    if user.email_verified:
        return JSONResponse(ok({"accepted": True, "already_verified": True}), status_code=202, headers={"Cache-Control": "no-store"})
    hit_rate_limit(db, scope="email_verification_resend", identity=str(user.id), limit=3, window_seconds=3600)
    _issue_email_verification(db, user)
    db.commit()
    return JSONResponse(ok({"accepted": True, "already_verified": False}), status_code=202, headers={"Cache-Control": "no-store"})


@router.post("/email/verification/confirm")
def confirm_email_verification(
    data: EmailVerificationConfirmIn,
    request: Request,
    db: Session = Depends(get_db),
):
    hit_rate_limit(db, scope="email_verification_confirm_ip", identity=client_ip(request), limit=30, window_seconds=3600)
    now = datetime.now(timezone.utc)
    token = db.query(EmailVerificationToken).filter(
        EmailVerificationToken.token_hash == digest(data.token)
    ).with_for_update().first()
    if token is None or token.used_at is not None or (
        token.expires_at if token.expires_at.tzinfo else token.expires_at.replace(tzinfo=timezone.utc)
    ) <= now:
        raise ApiError("EMAIL_VERIFICATION_TOKEN_INVALID", "验证链接无效或已过期", 400)
    user = db.get(User, token.user_id)
    if user is None or user.status != "active":
        raise ApiError("EMAIL_VERIFICATION_TOKEN_INVALID", "验证链接无效或已过期", 400)
    user.email_verified = True
    token.used_at = now
    db.query(EmailVerificationToken).filter(
        EmailVerificationToken.user_id == user.id,
        EmailVerificationToken.id != token.id,
        EmailVerificationToken.used_at.is_(None),
    ).update({EmailVerificationToken.used_at: now}, synchronize_session=False)
    db.commit()
    return JSONResponse(ok({"verified": True}), headers={"Cache-Control": "no-store"})


@router.post("/email/password-reset/confirm")
def confirm_password_reset(
    data: PasswordResetConfirmIn,
    request: Request,
    db: Session = Depends(get_db),
):
    hit_rate_limit(db, scope="password_reset_confirm_ip", identity=client_ip(request), limit=30, window_seconds=3600)
    now = datetime.now(timezone.utc)
    token = db.query(PasswordResetToken).filter(
        PasswordResetToken.token_hash == digest(data.token)
    ).with_for_update().first()
    if token is None or token.used_at is not None or (
        token.expires_at if token.expires_at.tzinfo else token.expires_at.replace(tzinfo=timezone.utc)
    ) <= now:
        raise ApiError("PASSWORD_RESET_TOKEN_INVALID", "重置链接无效或已过期", 400)
    user = db.get(User, token.user_id)
    if user is None or user.status != "active":
        raise ApiError("PASSWORD_RESET_TOKEN_INVALID", "重置链接无效或已过期", 400)
    if verify_password(data.password, user.password_hash):
        raise ApiError("PASSWORD_REUSE_FORBIDDEN", "新密码不能与当前密码相同", 409)
    user.password_hash = hash_password(data.password)
    token.used_at = now
    db.query(LoginSession).filter(
        LoginSession.user_id == user.id,
        LoginSession.revoked_at.is_(None),
    ).update({
        LoginSession.revoked_at: now,
        LoginSession.revoke_reason: "password_reset",
    }, synchronize_session=False)
    db.commit()
    response = JSONResponse(ok({"reset": True}))
    response.headers["Cache-Control"] = "no-store"
    return response


@router.post("/email/code")
def email_code(data: CodeRequestIn):
    if not settings.EMAIL_VERIFICATION_ENABLED:
        raise ApiError("EMAIL_PROVIDER_UNCONFIGURED", "邮箱验证码服务尚未配置", 503)
    raise ApiError("EMAIL_PROVIDER_PENDING", "邮箱验证码服务正在接入", 503)


@router.post("/phone/code")
def phone_code(data: CodeRequestIn):
    if not settings.SMS_PROVIDER_ENABLED:
        raise ApiError("SMS_PROVIDER_UNCONFIGURED", "短信服务尚未配置", 503)
    raise ApiError("SMS_PROVIDER_PENDING", "短信服务正在接入", 503)


@router.post("/phone/register")
@router.post("/phone/login")
def phone_auth(data: PhoneAuthIn):
    if not settings.SMS_PROVIDER_ENABLED:
        raise ApiError("SMS_PROVIDER_UNCONFIGURED", "短信服务尚未配置，暂时不能使用手机号认证", 503)
    raise ApiError("SMS_PROVIDER_PENDING", "手机号认证服务正在接入", 503)


@router.get("/kai/start")
def kai_start(return_to: str = "/account"):
    if not settings.KAI_AUTH_CLIENT_ID or not settings.KAI_AUTH_CALLBACK_URL:
        raise ApiError("KAI_UNCONFIGURED", "Kai 统一认证尚未配置", 503)
    raise ApiError("KAI_PENDING", "Kai 统一认证将在提供客户端凭据后完成最终联调", 503)


@router.get("/me")
def me(user: User = Depends(get_current_user)):
    return JSONResponse(ok({"user": _user_out(user)}), headers={"Cache-Control": "no-store"})


@router.post("/logout")
def logout(
    request: Request,
    user: User = Depends(require_csrf),
    db: Session = Depends(get_db),
):
    session = current_session(request, db)
    session.revoked_at = datetime.now(timezone.utc)
    session.revoke_reason = "user_logout"
    db.commit()
    response = JSONResponse(ok({"logged_out": True}))
    response.headers["Cache-Control"] = "no-store"
    response.delete_cookie(SESSION_COOKIE, path="/")
    response.delete_cookie(CSRF_COOKIE, path="/")
    return response
