import random
import string
from datetime import datetime, timezone
from decimal import Decimal

from fastapi import APIRouter, Depends, Query
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.core.deps import get_current_user
from app.db.session import get_db
from app.models.invite import INVITE_CODE_PREFIX, InviteCode, InviteRecord
from app.models.order import Order
from app.models.reward_accrual import RewardAccrual
from app.models.user import User
from app.services.reward_program import (
    PROGRAM_INVITE,
    PROGRAM_INVITE_COMMISSION,
    PROGRAM_INVITE_QUALIFICATION,
    program_enabled,
)
from app.services.reward_entitlements import INVITE_POLICY_VERSION, create_invite_accrual
from app.services.auth_session import normalize_platform
from app.services.invite_rewards_v2 import (
    INVITE_V2_DAILY_LIMIT,
    INVITE_V2_FIXED_REWARD,
    INVITE_V2_POLICY_VERSION,
    INVITE_V2_RELATIONSHIP_VERSION,
    INVITE_V2_TIMEZONE,
    STATUS_DAILY_CAP_EXCEEDED,
    STATUS_PENDING_IDENTITY,
    STATUS_PENDING_ORDER,
    STATUS_QUALIFIED,
    STATUS_RISK_REJECTED,
    STATUS_RISK_REVIEW,
    business_day,
    initialize_v2_relationship,
    invite_v2_enabled,
    invite_v2_reward_totals,
    next_reset_at,
    tier_rate_bps,
    tier_rows,
)
from app.models.invite import InviteDailyQuota
from app.schemas.invite import (
    InviteCommissionListResponse,
    InviteRelationshipListResponse,
    InviteSummaryResponse,
)
from app.utils.response import success

router = APIRouter(prefix="/api/invite", tags=["invite"])


def _gen_code(db: Session) -> str:
    chars = string.ascii_uppercase + string.digits
    while True:
        code = INVITE_CODE_PREFIX + "".join(random.choices(chars, k=6))
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


def create_invite_relationship(
    user: User,
    inviter_id: int,
    db: Session,
    *,
    platform: str = "legacy",
) -> InviteRecord:
    """Persist the relationship without granting anything to an unverified phone."""
    existing = db.query(InviteRecord).filter(InviteRecord.invitee_id == user.id).first()
    if existing:
        return existing
    source_platform = normalize_platform(platform)
    record = InviteRecord(
        inviter_id=inviter_id,
        invitee_id=user.id,
        invitee_phone=_mask_phone(user.phone),
        status="registered" if user.phone_bound else "unverified",
        reward_amount=0,
        created_platform=source_platform,
        last_modified_platform=source_platform,
    )
    # The active writer at relationship creation is the immutable cutover
    # boundary. A V1/offline relationship is never upgraded later merely by
    # flipping the V2 switch.
    if invite_v2_enabled():
        initialize_v2_relationship(record)
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
    record.last_modified_platform = "system"
    code = db.query(InviteCode).filter(InviteCode.user_id == record.inviter_id).first()
    if code:
        qualified = db.query(InviteRecord).filter(
            InviteRecord.inviter_id == record.inviter_id,
            InviteRecord.status.in_(["registered", "ordered", "rewarded"]),
        ).count()
        code.invited_count = qualified


def process_first_order_reward(user_id: int, order_id: int, db: Session) -> Decimal:
    """Reward a verified invitee's first confirmed usage order, exactly once."""
    if not program_enabled(PROGRAM_INVITE):
        return Decimal("0")
    user = db.query(User).filter(User.id == user_id).first()
    if not user or not user.invited_by:
        return Decimal("0")
    record = db.query(InviteRecord).filter(InviteRecord.invitee_id == user_id).first()
    if not record:
        record = create_invite_relationship(user, user.invited_by, db, platform="system")
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

    if record.status == "rewarded":
        return Decimal("0")

    qualified_count = db.query(InviteRecord).filter(
        InviteRecord.inviter_id == record.inviter_id,
        InviteRecord.status.in_(["registered", "ordered", "rewarded"]),
    ).count()
    rate = _get_tier_rate(qualified_count)
    now = datetime.now(timezone.utc)
    accrual = create_invite_accrual(
        beneficiary_user_id=record.inviter_id,
        order=order,
        rate_bps=int(rate * Decimal("10000")),
        event_at=now,
        db=db,
    )
    if not accrual:
        record.status = "ordered"
        record.last_modified_platform = "system"
        record.ordered_at = now
        return Decimal("0")
    db.refresh(accrual)
    record.status = "rewarded" if accrual.status == "settled" else "ordered"
    record.reward_amount = float(accrual.reward_amount)
    record.ordered_at = order.start_at
    record.rewarded_at = accrual.settled_at if accrual.status == "settled" else None
    record.last_modified_platform = "system"
    db.flush()
    return Decimal(str(accrual.reward_amount)) if accrual.status == "settled" else Decimal("0")


def _v2_next_tier_hint(qualified_count: int) -> str:
    for threshold, rate in ((5, 2), (10, 4), (15, 6), (20, 8)):
        if qualified_count < threshold:
            return f"再有 {threshold - qualified_count} 位好友达标升级至 {rate}%"
    return "已达最高 8% 返佣等级"


@router.get("/summary", response_model=InviteSummaryResponse)
def summary(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    invite_code = _get_or_create_code(user, db)
    records_query = db.query(InviteRecord).filter(InviteRecord.inviter_id == user.id)
    invited_count = records_query.count()
    now = datetime.now(timezone.utc)
    v2_active = invite_v2_enabled()
    has_v2_history = records_query.filter(
        InviteRecord.qualification_policy_version == INVITE_V2_RELATIONSHIP_VERSION,
    ).count() > 0 or db.query(RewardAccrual).filter(
        RewardAccrual.beneficiary_user_id == user.id,
        RewardAccrual.program_code.in_((
            PROGRAM_INVITE_COMMISSION,
            PROGRAM_INVITE_QUALIFICATION,
        )),
    ).count() > 0
    if v2_active or has_v2_history:
        qualified_count = records_query.filter(
            InviteRecord.qualification_policy_version == INVITE_V2_RELATIONSHIP_VERSION,
            InviteRecord.qualification_status == STATUS_QUALIFIED,
        ).count()
        pending_identity = records_query.filter(
            InviteRecord.qualification_policy_version == INVITE_V2_RELATIONSHIP_VERSION,
            InviteRecord.qualification_status == STATUS_PENDING_IDENTITY,
        ).count()
        pending_order = records_query.filter(
            InviteRecord.qualification_policy_version == INVITE_V2_RELATIONSHIP_VERSION,
            InviteRecord.qualification_status == STATUS_PENDING_ORDER,
        ).count()
        daily_cap_exceeded = records_query.filter(
            InviteRecord.qualification_policy_version == INVITE_V2_RELATIONSHIP_VERSION,
            InviteRecord.qualification_status == STATUS_DAILY_CAP_EXCEEDED,
        ).count()
        risk_rejected = records_query.filter(
            InviteRecord.qualification_policy_version == INVITE_V2_RELATIONSHIP_VERSION,
            InviteRecord.qualification_status == STATUS_RISK_REJECTED,
        ).count()
        risk_review = records_query.filter(
            InviteRecord.qualification_policy_version == INVITE_V2_RELATIONSHIP_VERSION,
            InviteRecord.qualification_status == STATUS_RISK_REVIEW,
        ).count()
        quota = db.query(InviteDailyQuota).filter(
            InviteDailyQuota.inviter_id == user.id,
            InviteDailyQuota.business_day == business_day(now),
        ).first()
        slots_used = min(int(quota.used_count or 0), INVITE_V2_DAILY_LIMIT) if quota else 0
        totals = invite_v2_reward_totals(user.id, db)
        fixed_total = totals["fixed_reward_total"]
        fixed_pending = totals["fixed_reward_pending"]
        commission_total = totals["commission_total"]
        commission_pending = totals["commission_pending"]
        rate_bps = tier_rate_bps(qualified_count)
        rewarded_count = records_query.join(
            RewardAccrual,
            RewardAccrual.id == InviteRecord.fixed_reward_accrual_id,
        ).filter(RewardAccrual.status == "settled").count()
        return success({
            "code": invite_code.code,
            "invited_count": invited_count,
            "qualified_count": qualified_count,
            "pending_identity_count": pending_identity,
            "pending_order_count": pending_order,
            "daily_cap_exceeded_count": daily_cap_exceeded,
            "risk_rejected_count": risk_rejected,
            "risk_review_count": risk_review,
            "unverified_count": pending_identity,
            "pending_count": pending_identity + pending_order,
            "rewarded_count": rewarded_count,
            "current_tier": f"{rate_bps / 100:g}%",
            "current_rate_bps": rate_bps,
            "next_tier_hint": (
                _v2_next_tier_hint(qualified_count)
                if v2_active
                else "返佣计划当前暂停，新消费暂不计提"
            ),
            "tiers": tier_rows(),
            "fixed_reward_card_hours": float(INVITE_V2_FIXED_REWARD),
            "fixed_reward_total": round(float(fixed_total), 3),
            "fixed_reward_pending": round(float(fixed_pending), 3),
            "commission_total": round(float(commission_total), 3),
            "commission_pending": round(float(commission_pending), 3),
            "total_eligible_consumption_card_hours": round(
                float(totals["eligible_consumption_total"]), 6
            ),
            "eligible_friend_spend_card_hours": round(
                float(totals["eligible_consumption_total"]), 6
            ),
            "total_reward": round(float(fixed_total + commission_total), 3),
            "pending_reward": round(float(fixed_pending + commission_pending), 3),
            "daily_limit": INVITE_V2_DAILY_LIMIT,
            "daily_used": slots_used,
            "daily_remaining": INVITE_V2_DAILY_LIMIT - slots_used,
            "daily_slots_used": slots_used,
            "daily_slots_remaining": INVITE_V2_DAILY_LIMIT - slots_used,
            "next_reset_at": next_reset_at(now),
            "rewards_enabled": v2_active,
            "rewards_withdrawable": False,
            "rewards_transferable": False,
            "reward_mode": "live" if v2_active else "disabled",
            "program_code": "invite_v2",
            "policy_version": INVITE_V2_POLICY_VERSION,
            "business_timezone": INVITE_V2_TIMEZONE,
            "qualification_requirement": "verified_identity_and_first_cash_order",
        })

    qualified_count = records_query.filter(
        InviteRecord.status.in_(["registered", "ordered", "rewarded"])
    ).count()
    pending = records_query.filter(InviteRecord.status.in_(["registered", "ordered"])).count()
    unverified = records_query.filter(InviteRecord.status == "unverified").count()
    rewarded = records_query.filter(InviteRecord.status == "rewarded").count()
    total_reward = db.query(func.coalesce(func.sum(RewardAccrual.reward_amount), 0)).filter(
        RewardAccrual.program_code == PROGRAM_INVITE,
        RewardAccrual.beneficiary_user_id == user.id,
        RewardAccrual.status == "settled",
    ).scalar() or 0
    pending_reward = db.query(func.coalesce(func.sum(RewardAccrual.reward_amount), 0)).filter(
        RewardAccrual.program_code == PROGRAM_INVITE,
        RewardAccrual.beneficiary_user_id == user.id,
        RewardAccrual.status == "pending",
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
        "total_reward": round(float(total_reward), 3),
        "pending_reward": round(float(pending_reward), 3),
        "pending_count": pending,
        "rewarded_count": rewarded,
        "current_tier": f"{int(rate * 100)}%",
        "current_rate_bps": int(rate * Decimal("10000")),
        "next_tier_hint": next_tier if program_enabled(PROGRAM_INVITE) else "返佣计划当前未开启",
        "tiers": [
            {"min_qualified_count": 0, "max_qualified_count": 5, "rate_bps": 1500},
            {"min_qualified_count": 6, "max_qualified_count": 20, "rate_bps": 2000},
            {"min_qualified_count": 21, "max_qualified_count": None, "rate_bps": 2500},
        ],
        "pending_identity_count": unverified,
        "pending_order_count": pending,
        "daily_cap_exceeded_count": 0,
        "risk_rejected_count": 0,
        "risk_review_count": 0,
        "fixed_reward_card_hours": float(INVITE_V2_FIXED_REWARD),
        "fixed_reward_total": 0,
        "fixed_reward_pending": 0,
        "commission_total": round(float(total_reward), 3),
        "commission_pending": round(float(pending_reward), 3),
        "total_eligible_consumption_card_hours": 0,
        "eligible_friend_spend_card_hours": 0,
        "daily_limit": INVITE_V2_DAILY_LIMIT,
        "daily_used": 0,
        "daily_remaining": INVITE_V2_DAILY_LIMIT,
        "daily_slots_used": 0,
        "daily_slots_remaining": INVITE_V2_DAILY_LIMIT,
        "next_reset_at": next_reset_at(now),
        "rewards_enabled": program_enabled(PROGRAM_INVITE),
        "rewards_withdrawable": False,
        "rewards_transferable": False,
        "reward_mode": "live" if program_enabled(PROGRAM_INVITE) else "disabled",
        "program_code": "invite_first_order_reward",
        "policy_version": INVITE_POLICY_VERSION,
        "business_timezone": INVITE_V2_TIMEZONE,
        "qualification_requirement": "verified_identity_and_first_cash_order",
    })


@router.get("/records", response_model=InviteRelationshipListResponse)
def records(
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=50, ge=1, le=100),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    query = db.query(InviteRecord).filter(InviteRecord.inviter_id == user.id)
    total = query.count()
    items = query.order_by(InviteRecord.created_at.desc(), InviteRecord.id.desc()).offset(
        (page - 1) * page_size
    ).limit(page_size).all()
    accrual_ids = {
        item.fixed_reward_accrual_id
        for item in items
        if item.fixed_reward_accrual_id is not None
    }
    accruals = {
        accrual.id: accrual
        for accrual in db.query(RewardAccrual).filter(
            RewardAccrual.id.in_(accrual_ids),
        ).all()
    } if accrual_ids else {}
    output = []
    for item in items:
        accrual = accruals.get(item.fixed_reward_accrual_id)
        is_v2 = item.qualification_policy_version == INVITE_V2_RELATIONSHIP_VERSION
        masked_phone = _mask_phone(item.invitee_phone)
        output.append({
            "id": item.id,
            "invitee_phone_masked": masked_phone,
            "invitee_phone": masked_phone,
            "status": item.status,
            "legacy_status": item.status,
            "reward_amount": item.reward_amount,
            "rewarded_at": item.rewarded_at,
            "qualification_status": item.qualification_status if is_v2 else "legacy_v1",
            "qualification_reason": item.qualification_reason if is_v2 else None,
            "identity_verified_at": item.identity_verified_at if is_v2 else None,
            "qualified_at": item.qualified_at if is_v2 else None,
            "qualification_day": item.qualification_day if is_v2 else None,
            "daily_slot": item.daily_slot if is_v2 else None,
            "qualification_order_id": item.qualification_order_id if is_v2 else None,
            "fixed_reward_amount": float(accrual.reward_amount) if accrual else 0,
            "fixed_reward_status": accrual.status if accrual else "not_applicable",
            "created_at": item.created_at,
        })
    return success({
        "total": total,
        "page": page,
        "page_size": page_size,
        "items": output,
    })


@router.get("/commissions", response_model=InviteCommissionListResponse)
def commissions(
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=50, ge=1, le=100),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    query = db.query(RewardAccrual).filter(
        RewardAccrual.beneficiary_user_id == user.id,
        RewardAccrual.program_code == PROGRAM_INVITE_COMMISSION,
    )
    total = query.count()
    items = query.order_by(RewardAccrual.created_at.desc(), RewardAccrual.id.desc()).offset(
        (page - 1) * page_size
    ).limit(page_size).all()
    order_ids = {item.order_id for item in items if item.order_id is not None}
    order_users = {
        order_id: user_id
        for order_id, user_id in db.query(Order.id, Order.user_id).filter(
            Order.id.in_(order_ids),
        ).all()
    } if order_ids else {}
    invitee_ids = set(order_users.values())
    invitee_phones = {
        invitee_id: invitee_phone
        for invitee_id, invitee_phone in db.query(
            InviteRecord.invitee_id,
            InviteRecord.invitee_phone,
        ).filter(
            InviteRecord.inviter_id == user.id,
            InviteRecord.invitee_id.in_(invitee_ids),
        ).all()
    } if invitee_ids else {}
    return success({
        "total": total,
        "page": page,
        "page_size": page_size,
        "items": [{
            "id": item.id,
            "invitee_phone_masked": _mask_phone(
                invitee_phones.get(order_users.get(item.order_id))
            ) if order_users.get(item.order_id) in invitee_phones else "",
            "source_type": item.source_type,
            "order_id": item.order_id,
            "order_renewal_id": item.order_renewal_id,
            "base_card_hours": float(item.base_amount),
            "rate_bps": item.rate_bps,
            "reward_card_hours": float(item.reward_amount),
            "status": item.status,
            "policy_version": item.policy_version,
            "created_at": item.created_at,
            "settled_at": item.settled_at,
        } for item in items],
    })
