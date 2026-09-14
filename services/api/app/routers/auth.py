from decimal import Decimal
import random, string
import logging

from fastapi import APIRouter, Depends, HTTPException, Query, status
from fastapi.responses import RedirectResponse
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.security import hash_password, verify_password
from app.core.config import settings
from app.core.deps import AuthContext, get_current_auth_context, get_current_user
from app.core.rate_limit import limit_captcha, limit_login, limit_register
from app.db.session import get_db
from app.models.external_identity import ExternalIdentity
from app.models.ledger import Ledger
from app.models.user import User
from app.models.wallet import Wallet
from app.models.invite import InviteCode, InviteRecord
from app.schemas.auth import KaiBindStartIn, KaiStartIn, KaiTicketIn
from app.schemas.user import LoginIn, RegisterIn, UserOut
from app.services.auth_session import (
    create_authenticated_session,
    resolve_client,
    revoke_current_session,
)
from app.utils.response import success, BizError
from app.utils.captcha import create_captcha, verify_captcha
from app.services import kai_auth
from app.services import account_recovery

INIT_BALANCE = Decimal("0")  # 无初始余额
router = APIRouter(prefix="/api/auth", tags=["auth"])
logger = logging.getLogger(__name__)


@router.get("/captcha", dependencies=[Depends(limit_captcha)])
def get_captcha():
    """获取图形验证码"""
    return success(create_captcha())


def _ensure_invite_code(user_id: int, db: Session) -> str:
    """Stage the user's invite code in the caller-owned transaction."""
    existing = db.query(InviteCode).filter(InviteCode.user_id == user_id).first()
    if existing:
        return existing.code
    code = "WOD" + "".join(random.choices(string.ascii_uppercase + string.digits, k=6))
    db.add(InviteCode(user_id=user_id, code=code, invited_count=0))
    db.flush()
    return code


@router.post("/register")
def register(data: RegisterIn, db: Session = Depends(get_db)):
    limit_register(data.phone)
    platform, client_id = resolve_client(data.client_id)
    # 图形验证码校验
    if not verify_captcha(data.captcha_key, data.captcha_code):
        raise BizError("验证码错误或已过期")
    if db.query(User).filter(User.phone == data.phone).first():
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "该手机号已注册")
    # 解析邀请码
    invite_code = data.invite_code if hasattr(data, 'invite_code') else None
    inviter = None
    if invite_code:
        inviter_code = db.query(InviteCode).filter(InviteCode.code == invite_code).first()
        if inviter_code:
            inviter = inviter_code
    # Password registration currently has only an image captcha. The phone remains a
    # login identifier and must not be represented as SMS-verified/bound.
    try:
        user = User(
            username=data.username,
            phone=data.phone,
            phone_bound=False,
            password=hash_password(data.password),
            created_platform=platform,
        )
        if inviter:
            user.invited_by = inviter.user_id
        db.add(user)
        db.flush()

        # Persist the relationship for the inviter's records, but keep it
        # unverified and grant no reward until phone ownership is verified and
        # a real test order has completed delivery.
        wallet = Wallet(user_id=user.id, balance=INIT_BALANCE, frozen=Decimal("0"))
        db.add(wallet)
        if inviter:
            from app.routers.invite import create_invite_relationship
            create_invite_relationship(user, inviter.user_id, db, platform=platform)
        db.flush()

        # The invite code and authentication session belong to the same
        # registration transaction. The session service performs the single
        # final commit after the JWT has been generated successfully.
        _ensure_invite_code(user.id, db)
        user_payload = UserOut.model_validate(user).model_dump()
        issued = create_authenticated_session(
            db,
            user,
            platform=platform,
            client_id=client_id,
            auth_method="password_register",
        )
    except IntegrityError as exc:
        db.rollback()
        if db.query(User).filter(User.phone == data.phone).first():
            raise HTTPException(status.HTTP_400_BAD_REQUEST, "该手机号已注册") from exc
        raise BizError("注册信息冲突，请重试", status_code=409) from exc
    except Exception:
        db.rollback()
        raise
    return success({"token": issued.token, "user": user_payload})


@router.post("/login")
def login(data: LoginIn, db: Session = Depends(get_db)):
    limit_login(data.phone)
    user = db.query(User).filter(User.phone == data.phone).first()
    if not user or not verify_password(data.password, user.password):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "手机号或密码错误")
    platform, client_id = resolve_client(data.client_id, user)
    issued = create_authenticated_session(
        db,
        user,
        platform=platform,
        client_id=client_id,
        auth_method="password",
    )
    return success({"token": issued.token, "user": UserOut.model_validate(user).model_dump()})


@router.post("/logout")
def logout(
    context: AuthContext = Depends(get_current_auth_context),
    db: Session = Depends(get_db),
):
    revoked = revoke_current_session(
        db,
        user_id=context.user.id,
        session_id=context.session_id,
    )
    return success({"logged_out": True, "session_revoked": revoked})


@router.get("/kai/config")
def kai_config():
    """Public capability status. Never exposes credentials or callback URLs."""
    return success(kai_auth.public_config())


@router.post("/kai/start")
def kai_start(data: KaiStartIn, db: Session = Depends(get_db)):
    platform, client_id = resolve_client(
        data.client_id,
        allow_admin_before_identity=True,
    )
    authorization_url = kai_auth.create_authorization_flow(
        db,
        data.intent,
        data.return_url,
        platform=platform,
        client_id=client_id,
    )
    return success({"authorization_url": authorization_url})


@router.get("/kai/status")
def kai_status(
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    identity = db.query(ExternalIdentity).filter(
        ExternalIdentity.user_id == user.id,
        ExternalIdentity.provider == "kai",
    ).first()
    return success({
        "bound": identity is not None,
        "provider": identity.provider if identity else None,
        "issuer": identity.issuer if identity else None,
    })


@router.post("/kai/bind/start")
def kai_bind_start(
    data: KaiBindStartIn,
    context: AuthContext = Depends(get_current_auth_context),
    db: Session = Depends(get_db),
):
    authorization_url = kai_auth.create_authorization_flow(
        db,
        "bind",
        data.return_url,
        user_id=context.user.id,
        platform=context.platform,
        client_id=context.client_id,
    )
    return success({"authorization_url": authorization_url})


@router.get("/kai/callback", response_class=RedirectResponse)
async def kai_callback(
    code: str | None = Query(default=None),
    state: str = Query(default=""),
    iss: str | None = Query(default=None),
    error: str | None = Query(default=None),
    db: Session = Depends(get_db),
):
    flow = kai_auth.get_flow(db, state)
    return_url = flow.return_url
    kai_auth.consume_flow(db, flow)
    if error:
        return RedirectResponse(kai_auth.append_return_params(return_url, kai_error="access_denied"), status_code=302)
    if not code:
        return RedirectResponse(kai_auth.append_return_params(return_url, kai_error="missing_code"), status_code=302)
    if iss and iss.rstrip("/") != settings.KAI_AUTH_ISSUER.rstrip("/"):
        return RedirectResponse(kai_auth.append_return_params(return_url, kai_error="invalid_issuer"), status_code=302)
    try:
        token_data = await kai_auth.exchange_authorization_code(code, flow)
        claims = await kai_auth.verify_id_token(token_data["id_token"], flow.nonce)
        claims = await kai_auth.enrich_with_userinfo(claims, token_data.get("access_token"))
        if flow.intent == "bind":
            if not flow.user_id:
                raise BizError("统一认证绑定目标无效")
            ticket = kai_auth.issue_bind_ticket(
                db,
                flow.user_id,
                claims,
                platform=flow.platform or "legacy",
                client_id=flow.client_id,
            )
            return RedirectResponse(
                kai_auth.append_return_params(return_url, kai_bind_ticket=ticket),
                status_code=302,
            )
        user = kai_auth.find_bound_user(db, claims)
        if not user:
            return RedirectResponse(
                kai_auth.append_return_params(return_url, kai_error="identity_not_bound"),
                status_code=302,
            )
        if flow.intent == "recover":
            recovery_token = account_recovery.issue_kai_recovery_token(db, user)
            return RedirectResponse(
                kai_auth.append_return_fragment(
                    return_url,
                    kai_recovery_token=recovery_token,
                ),
                status_code=302,
            )
        ticket = kai_auth.issue_handoff_ticket(
            db,
            user.id,
            platform=flow.platform or "legacy",
            client_id=flow.client_id,
        )
    except BizError:
        return RedirectResponse(kai_auth.append_return_params(return_url, kai_error="authorization_failed"), status_code=302)
    except Exception:
        logger.exception("Kai authentication callback failed")
        return RedirectResponse(kai_auth.append_return_params(return_url, kai_error="authorization_failed"), status_code=302)
    return RedirectResponse(kai_auth.append_return_params(return_url, kai_ticket=ticket), status_code=302)


@router.post("/kai/exchange")
def kai_exchange(data: KaiTicketIn, db: Session = Depends(get_db)):
    try:
        user, platform, client_id = kai_auth.consume_handoff_ticket(
            db,
            data.ticket,
            commit=False,
        )
        # Serialize before the final commit so a response-shaping failure does
        # not consume the one-time ticket without returning a usable session.
        user_payload = UserOut.model_validate(user).model_dump()
        issued = create_authenticated_session(
            db,
            user,
            platform=platform,
            client_id=client_id,
            auth_method="kai_oidc",
        )
    except Exception:
        db.rollback()
        raise
    return success({"token": issued.token, "user": user_payload})


@router.post("/kai/bind/exchange")
def kai_bind_exchange(
    data: KaiTicketIn,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    identity = kai_auth.bind_identity_with_ticket(db, data.ticket, user)
    return success({
        "bound": True,
        "provider": identity.provider,
        "issuer": identity.issuer,
        "user": UserOut.model_validate(user).model_dump(),
    })
