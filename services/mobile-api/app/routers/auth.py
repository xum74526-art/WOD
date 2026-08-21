from decimal import Decimal
import random, string
import logging

from fastapi import APIRouter, Depends, HTTPException, Query, status
from fastapi.responses import RedirectResponse
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.core.security import create_access_token, hash_password, verify_password
from app.core.config import settings
from app.core.rate_limit import limit_captcha, limit_login, limit_register
from app.db.session import get_db
from app.models.ledger import Ledger
from app.models.user import User
from app.models.wallet import Wallet
from app.models.invite import InviteCode, InviteRecord
from app.schemas.user import LoginIn, RegisterIn, UserOut
from app.utils.response import success, BizError
from app.utils.captcha import create_captcha, verify_captcha
from app.services import kai_auth

INIT_BALANCE = Decimal("0")  # 无初始余额
router = APIRouter(prefix="/api/auth", tags=["auth"])
logger = logging.getLogger(__name__)


class KaiStartIn(BaseModel):
    intent: str = "login"
    return_url: str | None = None


class KaiTicketIn(BaseModel):
    ticket: str


@router.get("/captcha", dependencies=[Depends(limit_captcha)])
def get_captcha():
    """获取图形验证码"""
    return success(create_captcha())


def _ensure_invite_code(user_id: int, db: Session) -> str:
    """自动生成邀请码"""
    existing = db.query(InviteCode).filter(InviteCode.user_id == user_id).first()
    if existing:
        return existing.code
    code = "WOD" + "".join(random.choices(string.ascii_uppercase + string.digits, k=6))
    db.add(InviteCode(user_id=user_id, code=code, invited_count=0))
    db.commit()
    return code


@router.post("/register")
def register(data: RegisterIn, db: Session = Depends(get_db)):
    limit_register(data.phone)
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
    # Closed-test registration has only an image captcha. The phone remains a
    # login identifier and must not be represented as SMS-verified/bound.
    user = User(
        username=data.username,
        phone=data.phone,
        phone_bound=False,
        password=hash_password(data.password),
    )
    if inviter:
        user.invited_by = inviter.user_id
    db.add(user)
    db.commit()
    db.refresh(user)
    # Persist the relationship for the inviter's records, but keep it
    # unverified and grant no reward until phone ownership is verified and a
    # real test order has completed delivery.
    total = Decimal("0")
    wallet = Wallet(user_id=user.id, balance=total, frozen=Decimal("0"))
    db.add(wallet)
    if inviter:
        from app.routers.invite import create_invite_relationship
        create_invite_relationship(user, inviter.user_id, db)
    db.commit()
    db.refresh(wallet)
    # 自动生成自己的邀请码
    _ensure_invite_code(user.id, db)
    token = create_access_token(user.id)
    return success({"token": token, "user": UserOut.model_validate(user).model_dump()})


@router.post("/login")
def login(data: LoginIn, db: Session = Depends(get_db)):
    limit_login(data.phone)
    user = db.query(User).filter(User.phone == data.phone).first()
    if not user or not verify_password(data.password, user.password):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "手机号或密码错误")
    token = create_access_token(user.id)
    return success({"token": token, "user": UserOut.model_validate(user).model_dump()})


@router.get("/kai/config")
def kai_config():
    """Public capability status. Never exposes credentials or callback URLs."""
    return success(kai_auth.public_config())


@router.post("/kai/start")
def kai_start(data: KaiStartIn, db: Session = Depends(get_db)):
    authorization_url = kai_auth.create_authorization_flow(db, data.intent, data.return_url)
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
        user = kai_auth.find_or_create_user(db, claims)
        ticket = kai_auth.issue_handoff_ticket(db, user.id)
    except BizError:
        return RedirectResponse(kai_auth.append_return_params(return_url, kai_error="authorization_failed"), status_code=302)
    except Exception:
        logger.exception("Kai authentication callback failed")
        return RedirectResponse(kai_auth.append_return_params(return_url, kai_error="authorization_failed"), status_code=302)
    return RedirectResponse(kai_auth.append_return_params(return_url, kai_ticket=ticket), status_code=302)


@router.post("/kai/exchange")
def kai_exchange(data: KaiTicketIn, db: Session = Depends(get_db)):
    user = kai_auth.consume_handoff_ticket(db, data.ticket)
    token = create_access_token(user.id)
    return success({"token": token, "user": UserOut.model_validate(user).model_dump()})
