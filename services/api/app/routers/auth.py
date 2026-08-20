import secrets
import re
from datetime import datetime, timedelta, timezone
from urllib.parse import quote, urlencode

from fastapi import APIRouter, Depends, Header, Request
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
    KaiExchangeIn,
    KaiStartIn,
    PasswordLoginIn,
    PasswordRegisterIn,
    TokenLoginIn,
    TokenRegisterIn,
)
from app.security import (
    CSRF_COOKIE,
    SESSION_COOKIE,
    ApiError,
    create_session,
    current_bearer_session,
    current_session,
    digest,
    get_current_user,
    get_bearer_user,
    hash_password,
    require_csrf,
    verify_password,
)
from app.services.auth_security import client_ip, clear_rate_limit, hit_rate_limit
from app.services import kai_auth

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
    _set_session_cookies(response, session_token, csrf_token)
    return response


def _set_session_cookies(response, session_token: str, csrf_token: str) -> None:
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


def _normalize_identifier(value: str) -> tuple[str, str]:
    identifier = value.strip()
    if "@" in identifier:
        email = identifier.casefold()
        if len(email) > 255 or email.startswith("@") or email.endswith("@"):
            raise ApiError("IDENTIFIER_INVALID", "请输入有效的邮箱或手机号", 422)
        return "email", email
    phone = re.sub(r"[\s()-]", "", identifier)
    if not re.fullmatch(r"\+?[0-9]{6,20}", phone):
        raise ApiError("IDENTIFIER_INVALID", "请输入有效的邮箱或手机号", 422)
    return "phone", phone


def _create_password_user(db: Session, *, display_name: str, identifier_value: str, password: str) -> User:
    kind, identifier = _normalize_identifier(identifier_value)
    existing = db.query(User).filter(
        User.email == identifier if kind == "email" else User.phone == identifier
    ).first()
    if existing:
        raise ApiError("IDENTIFIER_EXISTS", "该邮箱或手机号已注册", 409)
    user = User(
        display_name=display_name.strip(),
        email=identifier if kind == "email" else None,
        email_verified=False,
        phone=identifier if kind == "phone" else None,
        phone_verified=False,
        password_hash=hash_password(password),
        role="personal",
        status="active",
    )
    db.add(user)
    db.flush()
    if kind == "email" and settings.EMAIL_VERIFICATION_ENABLED:
        _issue_email_verification(db, user)
    db.commit()
    db.refresh(user)
    return user


def _password_user(db: Session, *, identifier_value: str, password: str) -> tuple[User, str]:
    kind, identifier = _normalize_identifier(identifier_value)
    user = db.query(User).filter(
        User.email == identifier if kind == "email" else User.phone == identifier
    ).first()
    if not user or not verify_password(password, user.password_hash):
        raise ApiError("INVALID_CREDENTIALS", "邮箱、手机号或密码不正确", 401)
    if user.status != "active":
        raise ApiError("ACCOUNT_UNAVAILABLE", "账户不可用", 403)
    return user, identifier


def _token_response(
    user: User,
    db: Session,
    request: Request,
    device_name: str | None,
    *,
    status_code: int = 200,
) -> JSONResponse:
    access_token, _ = create_session(
        user,
        db,
        request,
        channel="app",
        device_name=device_name,
    )
    response = JSONResponse(
        ok({
            "access_token": access_token,
            "token_type": "Bearer",
            "expires_in": settings.SESSION_TTL_DAYS * 24 * 60 * 60,
            "user": _user_out(user),
        }),
        status_code=status_code,
    )
    response.headers["Cache-Control"] = "no-store"
    return response


@router.post("/token/register")
def token_register(data: TokenRegisterIn, request: Request, db: Session = Depends(get_db)):
    hit_rate_limit(db, scope="register_ip", identity=client_ip(request), limit=100, window_seconds=3600)
    user = _create_password_user(
        db,
        display_name=data.display_name,
        identifier_value=data.identifier,
        password=data.password,
    )
    return _token_response(user, db, request, data.device_name, status_code=201)


@router.post("/token")
def token_login(data: TokenLoginIn, request: Request, db: Session = Depends(get_db)):
    hit_rate_limit(db, scope="login_ip", identity=client_ip(request), limit=60, window_seconds=900)
    try:
        user, identifier = _password_user(db, identifier_value=data.identifier, password=data.password)
    except ApiError as exc:
        _, identifier = _normalize_identifier(data.identifier)
        if exc.code == "INVALID_CREDENTIALS":
            hit_rate_limit(db, scope="login_account_failure", identity=identifier, limit=5, window_seconds=900)
        raise
    if not user:
        hit_rate_limit(db, scope="login_account_failure", identity=identifier, limit=5, window_seconds=900)
    clear_rate_limit(db, scope="login_account_failure", identity=identifier)
    return _token_response(user, db, request, data.device_name)


@router.post("/password/register")
def password_register(data: PasswordRegisterIn, request: Request, db: Session = Depends(get_db)):
    hit_rate_limit(db, scope="register_ip", identity=client_ip(request), limit=100, window_seconds=3600)
    user = _create_password_user(
        db,
        display_name=data.display_name,
        identifier_value=data.identifier,
        password=data.password,
    )
    return _session_response(user, db, request, status_code=201)


@router.post("/password/login")
def password_login(data: PasswordLoginIn, request: Request, db: Session = Depends(get_db)):
    hit_rate_limit(db, scope="login_ip", identity=client_ip(request), limit=60, window_seconds=900)
    try:
        user, identifier = _password_user(db, identifier_value=data.identifier, password=data.password)
    except ApiError as exc:
        _, identifier = _normalize_identifier(data.identifier)
        if exc.code == "INVALID_CREDENTIALS":
            hit_rate_limit(db, scope="login_account_failure", identity=identifier, limit=5, window_seconds=900)
        raise
    clear_rate_limit(db, scope="login_account_failure", identity=identifier)
    return _session_response(user, db, request)


@router.get("/token/me")
def token_me(user: User = Depends(get_bearer_user)):
    return JSONResponse(ok({"user": _user_out(user)}), headers={"Cache-Control": "no-store"})


@router.post("/token/revoke")
def token_revoke(
    authorization: str | None = Header(default=None),
    user: User = Depends(get_bearer_user),
    db: Session = Depends(get_db),
):
    session = current_bearer_session(authorization, db)
    if session.user_id != user.id:
        raise ApiError("SESSION_INVALID", "登录状态无效", 401)
    session.revoked_at = datetime.now(timezone.utc)
    session.revoke_reason = "user_logout"
    db.commit()
    return JSONResponse(ok({"revoked": True}), headers={"Cache-Control": "no-store"})


@router.post("/email/register")
def email_register(data: EmailRegisterIn, request: Request, db: Session = Depends(get_db)):
    hit_rate_limit(db, scope="register_ip", identity=client_ip(request), limit=100, window_seconds=3600)
    user = _create_password_user(
        db,
        display_name=data.name,
        identifier_value=str(data.email),
        password=data.password,
    )
    return _session_response(user, db, request, status_code=201)


@router.post("/email/login")
def email_login(data: EmailLoginIn, request: Request, db: Session = Depends(get_db)):
    email = str(data.email).strip().lower()
    hit_rate_limit(db, scope="login_ip", identity=client_ip(request), limit=60, window_seconds=900)
    try:
        user, _ = _password_user(db, identifier_value=email, password=data.password)
    except ApiError as exc:
        if exc.code == "INVALID_CREDENTIALS":
            hit_rate_limit(db, scope="login_account_failure", identity=email, limit=5, window_seconds=900)
        raise
    if not user:
        hit_rate_limit(db, scope="login_account_failure", identity=email, limit=5, window_seconds=900)
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


def _web_session_redirect(user: User, db: Session, request: Request, return_to: str) -> RedirectResponse:
    session_token, csrf_token = create_session(user, db, request, channel="web")
    destination = f"{settings.FRONTEND_BASE_URL.rstrip('/')}{kai_auth.safe_return_to(return_to)}"
    response = RedirectResponse(destination, status_code=302)
    response.headers["Cache-Control"] = "no-store"
    _set_session_cookies(response, session_token, csrf_token)
    return response


def _kai_redirect(base: str, key: str, value: str) -> str:
    separator = "&" if "?" in base else "?"
    return f"{base}{separator}{urlencode({key: value})}"


def _kai_error_code(error: ApiError) -> str:
    if error.code == "KAI_ACCESS_DENIED":
        return "access_denied"
    if error.code == "KAI_CODE_INVALID":
        return "missing_code"
    if error.code == "KAI_ISSUER_INVALID":
        return "invalid_issuer"
    if error.code == "KAI_ACCOUNT_NOT_FOUND":
        return "account_not_found"
    if error.code == "KAI_IDENTITY_CONFLICT":
        return "identity_conflict"
    return "authorization_failed"


def _kai_error_response(flow, error: ApiError) -> RedirectResponse:
    code = _kai_error_code(error)
    if flow is not None and flow.channel == "app":
        destination = _kai_redirect(settings.KAI_AUTH_APP_REDIRECT_URL, "kai_error", code)
    else:
        mode = "register" if flow is not None and flow.intent == "register" else "login"
        destination = _kai_redirect(f"{settings.FRONTEND_BASE_URL.rstrip('/')}/{mode}", "kai_error", code)
    return RedirectResponse(destination, status_code=302)


@router.get("/kai/start")
def kai_start(
    db: Session = Depends(get_db),
    intent: str = "login",
    return_to: str = "/account",
):
    authorization_url = kai_auth.start_flow(
        db,
        channel="web",
        intent=intent,
        return_to=return_to,
    )
    return RedirectResponse(authorization_url, status_code=302)


@router.get("/kai/config")
def kai_config():
    return ok(kai_auth.config_out())


@router.post("/kai/start")
def kai_app_start(data: KaiStartIn, db: Session = Depends(get_db)):
    return ok({
        "authorization_url": kai_auth.start_flow(
            db,
            channel="app",
            intent=data.intent,
            return_to="/",
        )
    })


@router.get("/kai/callback")
def kai_callback(
    request: Request,
    code: str | None = None,
    state: str | None = None,
    error: str | None = None,
    db: Session = Depends(get_db),
):
    flow = None
    try:
        if not state:
            raise ApiError("KAI_STATE_INVALID", "Kai 登录状态无效或已过期", 400)
        flow = kai_auth.consume_flow(db, state)
        if error:
            raise ApiError("KAI_ACCESS_DENIED", "已取消 Kai 授权", 400)
        profile = kai_auth.fetch_profile(code or "", flow)
        user = kai_auth.resolve_user(db, flow, profile)
        if flow.channel == "app":
            ticket = kai_auth.issue_app_ticket(db, user)
            destination = _kai_redirect(settings.KAI_AUTH_APP_REDIRECT_URL, "kai_ticket", ticket)
            return RedirectResponse(destination, status_code=302)
        return _web_session_redirect(user, db, request, flow.return_to)
    except ApiError as exc:
        return _kai_error_response(flow, exc)


@router.post("/kai/exchange")
def kai_app_exchange(data: KaiExchangeIn, request: Request, db: Session = Depends(get_db)):
    user = kai_auth.consume_app_ticket(db, data.ticket)
    return _token_response(user, db, request, "Kai 统一认证")


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
