"""Invitation V2 qualification, fixed bonus and cash-consumption commission."""

from datetime import date, datetime, time, timedelta, timezone
from decimal import Decimal
from zoneinfo import ZoneInfo

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.sensitive import fingerprint, reveal
from app.models.invite import InviteDailyQuota, InviteRecord
from app.models.order import Order
from app.models.order_funding import OrderFundingAllocation
from app.models.order_renewal import OrderRenewal
from app.models.reward_accrual import RewardAccrual
from app.models.user import User
from app.models.verification import Verification
from app.services.funding_allocation import cash_backed_amount, funding_amount
from app.services.reward_accrual import (
    create_reward_accrual,
    period_key,
    reward_money,
    settle_reward_accrual,
)
from app.services.reward_program import (
    PROGRAM_INVITE_COMMISSION,
    PROGRAM_INVITE_QUALIFICATION,
    program_enabled,
)


INVITE_V2_POLICY_VERSION = "invite-v2-2026-08"
INVITE_V2_RELATIONSHIP_VERSION = "invite-relationship-v2"
INVITE_V2_TIMEZONE = "Asia/Shanghai"
INVITE_V2_DAILY_LIMIT = 5
INVITE_V2_FIXED_REWARD = Decimal("58.00")
INVITE_V2_TIERS = (
    (0, 4, 0),
    (5, 9, 200),
    (10, 14, 400),
    (15, 19, 600),
    (20, None, 800),
)

STATUS_PENDING_IDENTITY = "pending_identity"
STATUS_PENDING_ORDER = "pending_order"
STATUS_QUALIFIED = "qualified"
STATUS_DAILY_CAP_EXCEEDED = "daily_cap_exceeded"
STATUS_RISK_REJECTED = "risk_rejected"
STATUS_RISK_REVIEW = "risk_review"
TERMINAL_STATUSES = {
    STATUS_QUALIFIED,
    STATUS_DAILY_CAP_EXCEEDED,
    STATUS_RISK_REJECTED,
}
FINAL_ORDER_STATUSES = ("completed", "running", "done")


def invite_v2_enabled() -> bool:
    return bool(
        program_enabled(PROGRAM_INVITE_QUALIFICATION)
        and program_enabled(PROGRAM_INVITE_COMMISSION)
    )


def tier_rate_bps(qualified_count: int) -> int:
    count = max(int(qualified_count or 0), 0)
    for minimum, maximum, rate_bps in INVITE_V2_TIERS:
        if count >= minimum and (maximum is None or count <= maximum):
            return rate_bps
    return 0


def tier_rows() -> list[dict]:
    return [
        {
            "min_qualified_count": minimum,
            "max_qualified_count": maximum,
            "rate_bps": rate_bps,
        }
        for minimum, maximum, rate_bps in INVITE_V2_TIERS
    ]


def _as_utc(value: datetime | None) -> datetime:
    current = value or datetime.now(timezone.utc)
    return current.replace(tzinfo=timezone.utc) if current.tzinfo is None else current.astimezone(timezone.utc)


def business_day(value: datetime | None = None) -> date:
    return _as_utc(value).astimezone(ZoneInfo(INVITE_V2_TIMEZONE)).date()


def next_reset_at(value: datetime | None = None) -> datetime:
    local = _as_utc(value).astimezone(ZoneInfo(INVITE_V2_TIMEZONE))
    next_day = local.date() + timedelta(days=1)
    return datetime.combine(next_day, time.min, ZoneInfo(INVITE_V2_TIMEZONE)).astimezone(timezone.utc)


def is_v2_relationship(record: InviteRecord | None) -> bool:
    return bool(record and record.qualification_policy_version == INVITE_V2_RELATIONSHIP_VERSION)


def initialize_v2_relationship(record: InviteRecord) -> None:
    """Mark only newly-created relationships as V2 candidates."""

    record.qualification_policy_version = INVITE_V2_RELATIONSHIP_VERSION
    record.qualification_status = STATUS_PENDING_IDENTITY
    record.qualification_reason = "verified_identity_required"


def _verified_identity(user_id: int, db: Session) -> Verification | None:
    return db.query(Verification).filter(
        Verification.user_id == user_id,
        Verification.status == "verified",
    ).first()


def _same_verified_identity(
    inviter_id: int,
    invitee_verification: Verification,
    db: Session,
) -> bool | None:
    invitee_plain = reveal(invitee_verification.id_card)
    if not invitee_plain:
        return None
    inviter_verification = _verified_identity(inviter_id, db)
    if inviter_verification is None:
        return False
    inviter_plain = reveal(inviter_verification.id_card)
    if not inviter_plain:
        # Failed decryption is not silently treated as a successful identity
        # comparison. Qualification remains blocked for explicit review.
        return None
    return fingerprint(invitee_plain) == fingerprint(inviter_plain)


def _first_cash_backed_order(user_id: int, db: Session) -> Order | None:
    return db.query(Order).join(
        OrderFundingAllocation,
        OrderFundingAllocation.order_id == Order.id,
    ).filter(
        Order.user_id == user_id,
        Order.status.in_(FINAL_ORDER_STATUSES),
        Order.confirmed_at.isnot(None),
        OrderFundingAllocation.source_type == "order",
        OrderFundingAllocation.status == "captured",
        OrderFundingAllocation.cash_amount > 0,
    ).order_by(Order.confirmed_at.asc(), Order.id.asc()).first()


def _qualified_count(inviter_id: int, db: Session) -> int:
    return db.query(InviteRecord).filter(
        InviteRecord.inviter_id == inviter_id,
        InviteRecord.qualification_policy_version == INVITE_V2_RELATIONSHIP_VERSION,
        InviteRecord.qualification_status == STATUS_QUALIFIED,
    ).count()


def _claim_daily_slot(inviter_id: int, event_at: datetime, db: Session) -> tuple[date, int | None]:
    # The inviter row is the portable serialization lock for all dates. Order
    # confirmation already holds a SQLite write transaction; PostgreSQL honors
    # FOR UPDATE here, and the unique quota row is the final database boundary.
    inviter = db.query(User).filter(User.id == inviter_id).with_for_update().first()
    if inviter is None:
        return business_day(event_at), None
    day = business_day(event_at)
    quota = db.query(InviteDailyQuota).filter(
        InviteDailyQuota.inviter_id == inviter_id,
        InviteDailyQuota.business_day == day,
    ).with_for_update().first()
    if quota is None:
        quota = InviteDailyQuota(
            inviter_id=inviter_id,
            business_day=day,
            used_count=0,
            policy_version=INVITE_V2_POLICY_VERSION,
        )
        db.add(quota)
        db.flush()
    if int(quota.used_count or 0) >= INVITE_V2_DAILY_LIMIT:
        return day, None
    quota.used_count = int(quota.used_count or 0) + 1
    db.flush()
    return day, int(quota.used_count)


def _create_fixed_bonus(record: InviteRecord, event_at: datetime, db: Session) -> RewardAccrual:
    key = f"reward:{PROGRAM_INVITE_QUALIFICATION}:invite_record:{record.id}"
    accrual, _ = create_reward_accrual(
        db,
        program_code=PROGRAM_INVITE_QUALIFICATION,
        policy_version=INVITE_V2_POLICY_VERSION,
        beneficiary_user_id=record.inviter_id,
        source_type="invite_record",
        source_id=record.id,
        order_id=record.qualification_order_id,
        order_renewal_id=None,
        asset_id=None,
        period=period_key(event_at),
        base_amount=INVITE_V2_FIXED_REWARD,
        rate_bps=10000,
        reward_amount=INVITE_V2_FIXED_REWARD,
        policy_snapshot={
            "fixed_reward_card_hours": float(INVITE_V2_FIXED_REWARD),
            "requirements": ["verified_identity", "first_cash_backed_confirmed_order"],
            "business_timezone": INVITE_V2_TIMEZONE,
            "daily_limit": INVITE_V2_DAILY_LIMIT,
            "qualification_day": record.qualification_day.isoformat() if record.qualification_day else None,
            "daily_slot": record.daily_slot,
            "withdrawable": False,
            "one_level_only": True,
        },
        due_at=event_at,
        idempotency_key=key,
    )
    if settings.REWARD_SETTLEMENT_ENABLED:
        settle_reward_accrual(accrual.id, db)
    record.fixed_reward_accrual_id = accrual.id
    return accrual


def reevaluate_invitee_qualification(
    user_id: int,
    db: Session,
    *,
    event_at: datetime | None = None,
) -> InviteRecord | None:
    """Evaluate the two qualification facts without creating past commission."""

    if not invite_v2_enabled():
        return None
    now = _as_utc(event_at)
    record = db.query(InviteRecord).filter(
        InviteRecord.invitee_id == user_id,
    ).with_for_update().first()
    if not is_v2_relationship(record):
        return record
    # Deletion terminates future participation, not previously earned rights.
    from app.services.account_lifecycle import try_lock_active_user
    for owner in sorted({record.inviter_id, record.invitee_id}):
        if not try_lock_active_user(db, owner):
            return record
    if record.qualification_status in TERMINAL_STATUSES:
        return record
    if record.inviter_id == record.invitee_id:
        record.qualification_status = STATUS_RISK_REJECTED
        record.qualification_reason = "self_invite"
        db.flush()
        return record

    verification = _verified_identity(user_id, db)
    if verification is None:
        record.qualification_status = STATUS_PENDING_IDENTITY
        record.qualification_reason = "verified_identity_required"
        db.flush()
        return record
    record.identity_verified_at = verification.updated_at or verification.created_at or now
    identity_match = _same_verified_identity(record.inviter_id, verification, db)
    if identity_match is None:
        record.qualification_status = STATUS_RISK_REVIEW
        record.qualification_reason = "identity_comparison_unavailable"
        db.flush()
        return record
    if identity_match:
        record.qualification_status = STATUS_RISK_REJECTED
        record.qualification_reason = "same_verified_identity"
        db.flush()
        return record

    first_order = _first_cash_backed_order(user_id, db)
    if first_order is None:
        record.qualification_status = STATUS_PENDING_ORDER
        record.qualification_reason = "first_cash_backed_order_required"
        db.flush()
        return record

    day, slot = _claim_daily_slot(record.inviter_id, now, db)
    record.qualification_day = day
    record.qualification_order_id = first_order.id
    if slot is None:
        record.qualification_status = STATUS_DAILY_CAP_EXCEEDED
        record.qualification_reason = "daily_qualified_limit_reached"
        record.daily_slot = None
        db.flush()
        return record

    record.qualification_status = STATUS_QUALIFIED
    record.qualification_reason = "verified_identity_and_first_cash_order"
    record.qualified_at = now
    record.daily_slot = slot
    db.flush()
    _create_fixed_bonus(record, now, db)
    return record


def _create_commission(
    record: InviteRecord,
    *,
    source_type: str,
    source_id: int,
    order: Order,
    renewal: OrderRenewal | None,
    event_at: datetime,
    db: Session,
) -> RewardAccrual | None:
    if record.qualification_status != STATUS_QUALIFIED or record.qualified_at is None:
        return None
    if _as_utc(record.qualified_at) > _as_utc(event_at):
        # A later identity approval may grant the fixed 58 CH, but never
        # retrospectively commissions an already-confirmed consumption event.
        return None
    key = f"reward:{PROGRAM_INVITE_COMMISSION}:{source_type}:{source_id}"
    existing = db.query(RewardAccrual).filter(RewardAccrual.idempotency_key == key).first()
    if existing:
        return existing
    # Serialize the tier snapshot against a concurrent new qualification for
    # this inviter. The same row is locked while daily slots are claimed.
    inviter = db.query(User).filter(User.id == record.inviter_id).with_for_update().first()
    if inviter is None:
        return None
    from app.services.account_lifecycle import try_lock_active_user
    if not try_lock_active_user(db, record.inviter_id):
        return None
    existing = db.query(RewardAccrual).filter(RewardAccrual.idempotency_key == key).first()
    if existing:
        return existing
    base = cash_backed_amount(db, source_type=source_type, source_id=source_id)
    allocation = db.query(OrderFundingAllocation).filter(
        OrderFundingAllocation.source_type == source_type,
        OrderFundingAllocation.source_id == source_id,
    ).first()
    if allocation is None:
        return None
    qualified_count = _qualified_count(record.inviter_id, db)
    rate_bps = tier_rate_bps(qualified_count)
    reward = reward_money(base * Decimal(rate_bps) / Decimal("10000"))
    accrual, _ = create_reward_accrual(
        db,
        program_code=PROGRAM_INVITE_COMMISSION,
        policy_version=INVITE_V2_POLICY_VERSION,
        beneficiary_user_id=record.inviter_id,
        source_type=source_type,
        source_id=source_id,
        order_id=order.id,
        order_renewal_id=renewal.id if renewal is not None else None,
        asset_id=None,
        period=period_key(event_at),
        base_amount=base,
        rate_bps=rate_bps,
        reward_amount=reward,
        policy_snapshot={
            "qualified_count_at_event": qualified_count,
            "tiers": tier_rows(),
            "rate_bps": rate_bps,
            "non_retroactive": True,
            "one_level_only": True,
            "withdrawable": False,
            "funding_allocation_id": allocation.id,
            "funding_policy_version": allocation.policy_version,
            "gross_card_hours": float(funding_amount(allocation.gross_amount)),
            "cash_backed_card_hours": float(base),
            "promotional_card_hours": float(funding_amount(allocation.promotional_amount)),
            "merchant_settlement_basis": "full_gross_amount",
            "promotional_merchant_treatment": "platform_subsidy",
        },
        due_at=event_at,
        idempotency_key=key,
    )
    # A zero-rate row is deliberately settled too: it permanently snapshots
    # this event and prevents a later tier increase from being back-applied.
    if settings.REWARD_SETTLEMENT_ENABLED:
        settle_reward_accrual(accrual.id, db)
    return accrual


def process_invite_order_event(
    order: Order,
    db: Session,
    *,
    event_at: datetime | None = None,
) -> RewardAccrual | None:
    if not invite_v2_enabled() or order.status not in FINAL_ORDER_STATUSES:
        return None
    confirmed_at = _as_utc(order.confirmed_at or event_at)
    record = reevaluate_invitee_qualification(order.user_id, db, event_at=confirmed_at)
    if not is_v2_relationship(record):
        return None
    return _create_commission(
        record,
        source_type="order",
        source_id=order.id,
        order=order,
        renewal=None,
        event_at=confirmed_at,
        db=db,
    )


def process_invite_renewal_event(
    order: Order,
    renewal: OrderRenewal,
    db: Session,
    *,
    event_at: datetime | None = None,
) -> RewardAccrual | None:
    if not invite_v2_enabled() or order.status not in FINAL_ORDER_STATUSES:
        return None
    occurred_at = _as_utc(event_at or renewal.created_at)
    record = reevaluate_invitee_qualification(order.user_id, db, event_at=occurred_at)
    if not is_v2_relationship(record):
        return None
    return _create_commission(
        record,
        source_type="renewal",
        source_id=renewal.id,
        order=order,
        renewal=renewal,
        event_at=occurred_at,
        db=db,
    )


def invite_v2_reward_totals(user_id: int, db: Session) -> dict[str, Decimal]:
    def total(program: str, status: str) -> Decimal:
        value = db.query(func.coalesce(func.sum(RewardAccrual.reward_amount), 0)).filter(
            RewardAccrual.beneficiary_user_id == user_id,
            RewardAccrual.program_code == program,
            RewardAccrual.status == status,
        ).scalar()
        return Decimal(str(value or 0))

    return {
        "fixed_reward_total": total(PROGRAM_INVITE_QUALIFICATION, "settled"),
        "fixed_reward_pending": total(PROGRAM_INVITE_QUALIFICATION, "pending"),
        "commission_total": total(PROGRAM_INVITE_COMMISSION, "settled"),
        "commission_pending": total(PROGRAM_INVITE_COMMISSION, "pending"),
        "eligible_consumption_total": Decimal(str(
            db.query(func.coalesce(func.sum(RewardAccrual.base_amount), 0)).filter(
                RewardAccrual.beneficiary_user_id == user_id,
                RewardAccrual.program_code == PROGRAM_INVITE_COMMISSION,
                RewardAccrual.status.in_(("pending", "settled")),
            ).scalar() or 0
        )),
    }
