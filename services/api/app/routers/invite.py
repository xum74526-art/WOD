import random
import string
from datetime import datetime, timezone
from decimal import Decimal, ROUND_HALF_UP

from fastapi import APIRouter, Depends
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.core.deps import get_current_user
from app.db.session import get_db
from app.models.invite import InviteCode, InviteRecord
from app.models.ledger import Ledger
from app.models.order import Order
from app.models.user import User
from app.models.wallet import Wallet
from app.services.reward_program import (
    reward_ledger_type,
    reward_mode,
    reward_program_enabled,
)
from app.utils.response import success

router = APIRouter(prefix="/api/invite", tags=["invite"])


def _gen_code(db: Session) -> str:
    chars = string.ascii_uppercase + string.digits
    while True:
        code = "WOD" + "".join(random.choices(chars, k=6))
        if not db.query(InviteCode).filter(InviteCode.code == code).first():
            return code


def _get_or_create_code(user: User, db: Session) -> InviteCode:
    code = db.query(InviteCode).filter(InviteCode.user_id == user.id).first()
    if not code:
        code = InviteCode(user_id=user.id, code=_gen_code(db), invited_count=0)
        db.add(code)
        db.commit()
        db.refresh(code)
    return code


def _get_tier_rate(qualified_count: int) -> Decimal:
    if qualified_count <= 5:
        return Decimal("0.15")
    if qualified_count <= 20:
        return Decimal("0.20")
    return Decimal("0.25")


def _mask_phone(phone: str | None) -> str:
    value = str(phone or "")
    if len(value) >= 7:
        return f"{value[:3]}****{value[-4:]}"
    return "未绑定手机号"


def create_invite_relationship(user: User, inviter_id: int, db: Session) -> InviteRecord:
    """Persist the relationship without granting anything to an unverified phone."""
    existing = db.query(InviteRecord).filter(InviteRecord.invitee_id == user.id).first()
    if existing:
        return existing
    record = InviteRecord(
        inviter_id=inviter_id,
        invitee_id=user.id,
        invitee_phone=_mask_phone(user.phone),
        status="registered" if user.phone_bound else "unverified",
        reward_amount=0,
    )
    db.add(record)
    if user.phone_bound:
        code = db.query(InviteCode).filter(InviteCode.user_id == inviter_id).first()
        if code:
            code.invited_count = int(code.invited_count or 0) + 1
    db.flush()
    return record


def _promote_verified_relationship(user: User, record: InviteRecord, db: Session) -> None:
    if not user.phone_bound or record.status != "unverified":
        return
    record.status = "registered"
    code = db.query(InviteCode).filter(InviteCode.user_id == record.inviter_id).first()
    if code:
        qualified = db.query(InviteRecord).filter(
            InviteRecord.inviter_id == record.inviter_id,
            InviteRecord.status.in_(["registered", "ordered", "rewarded"]),
        ).count()
        code.invited_count = qualified


def process_first_order_reward(user_id: int, order_id: int, db: Session) -> Decimal:
    """Reward a verified invitee's first confirmed usage order, exactly once."""
    if not reward_program_enabled():
        return Decimal("0")
    user = db.query(User).filter(User.id == user_id).first()
    if not user or not user.invited_by:
        return Decimal("0")
    record = db.query(InviteRecord).filter(InviteRecord.invitee_id == user_id).first()
    if not record:
        record = create_invite_relationship(user, user.invited_by, db)
    _promote_verified_relationship(user, record, db)
    if not user.phone_bound or record.status not in ("registered", "ordered"):
        return Decimal("0")

    order = db.query(Order).filter(
        Order.id == order_id,
        Order.user_id == user_id,
        Order.status.in_(["completed", "running"]),
    ).first()
    if not order:
        return Decimal("0")
    first_order = db.query(Order).filter(
        Order.user_id == user_id,
        Order.status.in_(["completed", "running"]),
    ).order_by(Order.start_at.asc(), Order.id.asc()).first()
    if not first_order or first_order.id != order.id:
        return Decimal("0")

    ledger_type = reward_ledger_type("invite")
    existing = db.query(Ledger).filter(
        Ledger.user_id == record.inviter_id,
        Ledger.type == ledger_type,
        Ledger.ref_order_id == order.id,
    ).first()
    if existing or record.status == "rewarded":
        return Decimal("0")

    qualified_count = db.query(InviteRecord).filter(
        InviteRecord.inviter_id == record.inviter_id,
        InviteRecord.status.in_(["registered", "ordered", "rewarded"]),
    ).count()
    rate = _get_tier_rate(qualified_count)
    reward = (Decimal(str(order.amount or 0)) * rate).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    wallet = db.query(Wallet).filter(Wallet.user_id == record.inviter_id).with_for_update().first()
    if reward <= 0 or not wallet:
        record.status = "ordered"
        record.ordered_at = datetime.now(timezone.utc)
        return Decimal("0")

    wallet.balance = Decimal(str(wallet.balance or 0)) + reward
    db.add(Ledger(
        user_id=record.inviter_id,
        wallet_id=wallet.id,
        type=ledger_type,
        direction="in",
        amount=reward,
        balance_after=wallet.balance,
        ref_order_id=order.id,
        remark=f"邀请好友首单返利({int(rate * 100)}%)",
    ))
    record.status = "rewarded"
    record.reward_amount = float(reward)
    record.ordered_at = order.start_at
    record.rewarded_at = datetime.now(timezone.utc)
    db.flush()
    return reward


@router.get("/summary")
def summary(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    invite_code = _get_or_create_code(user, db)
    records_query = db.query(InviteRecord).filter(InviteRecord.inviter_id == user.id)
    invited_count = records_query.count()
    qualified_count = records_query.filter(
        InviteRecord.status.in_(["registered", "ordered", "rewarded"])
    ).count()
    pending = records_query.filter(InviteRecord.status.in_(["registered", "ordered"])).count()
    unverified = records_query.filter(InviteRecord.status == "unverified").count()
    rewarded = records_query.filter(InviteRecord.status == "rewarded").count()
    total_reward = records_query.with_entities(
        func.coalesce(func.sum(InviteRecord.reward_amount), 0)
    ).scalar() or 0

    rate = _get_tier_rate(qualified_count)
    if qualified_count <= 5:
        next_tier = f"再邀请 {6 - qualified_count} 人升级至 20% 返利"
    elif qualified_count <= 20:
        next_tier = f"再邀请 {21 - qualified_count} 人升级至 25% 返利"
    else:
        next_tier = "已达最高返利等级"

    return success({
        "code": invite_code.code,
        "invited_count": invited_count,
        "qualified_count": qualified_count,
        "unverified_count": unverified,
        "total_reward": round(float(total_reward), 2),
        "pending_count": pending,
        "rewarded_count": rewarded,
        "current_tier": f"{int(rate * 100)}%",
        "next_tier_hint": next_tier if reward_program_enabled() else "返佣计划当前未开启",
        "rewards_enabled": reward_program_enabled(),
        "reward_mode": reward_mode(),
    })


@router.get("/records")
def records(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    items = db.query(InviteRecord).filter(
        InviteRecord.inviter_id == user.id
    ).order_by(InviteRecord.created_at.desc()).limit(50).all()
    return success({
        "total": len(items),
        "items": [{
            "id": item.id,
            "invitee_phone": item.invitee_phone,
            "status": item.status,
            "reward_amount": item.reward_amount,
            "created_at": item.created_at.isoformat() if item.created_at else None,
            "rewarded_at": item.rewarded_at.isoformat() if item.rewarded_at else None,
        } for item in items],
    })
