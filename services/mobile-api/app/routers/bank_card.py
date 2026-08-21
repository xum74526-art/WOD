from datetime import datetime, timezone

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from sqlalchemy.exc import IntegrityError

from app.core.config import settings
from app.core.deps import get_current_user
from app.core.sensitive import (
    fingerprint,
    mask_bank_card,
    protect,
    reveal,
    sensitive_capability_enabled,
)
from app.db.session import get_db
from app.models.bank_card import BankCard, REGISTERED_CARD_STATUSES, public_bank_card_status
from app.models.verification import Verification
from app.models.user import User
from app.models.withdrawal import WithdrawalOrder
from app.schemas.bank_card import BankCardIn
from app.utils.bank_util import luhn_check, detect_bank, validate_phone
from app.utils.response import BizError, success

router = APIRouter(prefix="/api/bank-cards", tags=["bank-card"])


def _mask_phone(phone: str | None) -> str | None:
    if not phone or len(phone) < 7:
        return None
    return phone[:3] + "****" + phone[-4:]


def _card_out(card: BankCard) -> dict:
    plain_phone = reveal(card.phone)
    return {
        "id": card.id,
        "bank_name": card.bank_name,
        "card_number": mask_bank_card(card.card_number),
        "card_last4": reveal(card.card_number)[-4:],
        "holder": card.holder,
        "phone": _mask_phone(plain_phone),
        "is_default": card.is_default,
        "status": public_bank_card_status(card.status),
        "verification_mode": card.verification_mode or "legacy_unvalidated",
        "bank_verified": False,
        "reject_reason": card.review_reason,
        "reviewed_at": card.reviewed_at,
        "created_at": card.created_at,
    }


@router.get("")
def list_cards(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    items = db.query(BankCard).filter(BankCard.user_id == user.id).order_by(
        BankCard.is_default.desc(), BankCard.created_at.desc()
    ).all()
    return success([_card_out(c) for c in items])


@router.get("/config")
def bank_card_config(user: User = Depends(get_current_user)):
    return success({
        "binding_enabled": sensitive_capability_enabled(settings.MANUAL_BANK_CARD_ENABLED),
        "mode": "format_only",
        "bank_verified": False,
        "notice": "银行卡仅完成格式、Luhn 与实名姓名一致性登记，未经银行验证",
    })


@router.post("")
def add_card(data: BankCardIn, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    if not sensitive_capability_enabled(settings.MANUAL_BANK_CARD_ENABLED):
        raise BizError("银行卡登记服务尚未启用", status_code=503)
    # 1. 卡号Luhn校验
    if not luhn_check(data.card_number):
        raise BizError("卡号校验失败，请检查卡号是否正确")
    # 2. 手机号格式校验
    if not validate_phone(data.phone):
        raise BizError("手机号格式不正确")
    # 3. 持卡人实名关联：检查是否与实名认证一致
    verification = db.query(Verification).filter(Verification.user_id == user.id).first()
    if not verification or verification.status not in {"pending", "verified"}:
        raise BizError("请先提交实名认证资料")
    if data.holder != verification.real_name:
        raise BizError(f"持卡人姓名须与实名认证一致（{verification.real_name}）")
    # 4. BIN 仅用于无冲突时给出银行名称建议，不构成银行验证。
    bank_name = data.bank_name
    if not bank_name:
        detected = detect_bank(data.card_number)
        if detected:
            bank_name = detected
        else:
            raise BizError("无法识别银行卡所属银行，请手动填写银行名称")
    # 5. 重复卡号检查
    normalized_number = data.card_number
    card_fingerprint = fingerprint(normalized_number)
    existing = db.query(BankCard).filter(
        BankCard.user_id == user.id,
        BankCard.card_fingerprint == card_fingerprint,
    ).first()
    if not existing:
        # Compatibility for rows created before the fingerprint column.
        existing = next(
            (card for card in db.query(BankCard).filter(BankCard.user_id == user.id).all()
             if reveal(card.card_number).replace(" ", "") == normalized_number),
            None,
        )
    if existing:
        raise BizError("该银行卡已登记")
    has_default = db.query(BankCard).filter(
        BankCard.user_id == user.id,
        BankCard.status.in_(REGISTERED_CARD_STATUSES),
        BankCard.is_default.is_(True),
    ).first()
    c = BankCard(
        user_id=user.id, bank_name=bank_name, card_number=protect(normalized_number),
        holder=data.holder, phone=protect(data.phone),
        is_default=bool((data.is_default or not has_default) and not has_default),
        card_fingerprint=card_fingerprint, status="registered",
        verification_mode="format_only",
    )
    db.add(c)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise BizError("该银行卡已登记", status_code=409)
    db.refresh(c)
    return success(_card_out(c))


@router.post("/{cid}/default")
def set_default(cid: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    c = db.query(BankCard).filter(
        BankCard.id == cid,
        BankCard.user_id == user.id,
        BankCard.status.in_(REGISTERED_CARD_STATUSES),
    ).first()
    if not c:
        raise BizError("仅已登记且未停用的银行卡可设为默认卡", status_code=404)
    db.query(BankCard).filter(BankCard.user_id == user.id).update({"is_default": False})
    c.is_default = True
    db.commit()
    return success({"id": cid, "is_default": True})


@router.delete("/{cid}")
def delete_card(cid: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    c = db.query(BankCard).filter(BankCard.id == cid, BankCard.user_id == user.id).first()
    if not c:
        raise BizError("银行卡不存在", status_code=404)
    active_withdrawal = db.query(WithdrawalOrder).filter(
        WithdrawalOrder.bank_card_id == c.id,
        WithdrawalOrder.status.in_(("reviewing", "manual_payment_pending")),
    ).first()
    if active_withdrawal:
        raise BizError("该银行卡有关联的处理中提现申请，暂不能解绑")
    c.status = "disabled"
    c.is_default = False
    c.review_reason = "用户解绑"
    c.reviewed_at = datetime.now(timezone.utc).replace(tzinfo=None)
    db.commit()
    return success({"id": cid, "deleted": True, "status": "disabled"})
