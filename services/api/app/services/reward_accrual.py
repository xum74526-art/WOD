"""Durable, versioned reward entitlements and idempotent wallet credits."""

from datetime import datetime, timezone
from decimal import Decimal, ROUND_HALF_UP
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from sqlalchemy.orm import Session

from app.models.ledger import Ledger
from app.models.reward_accrual import RewardAccrual
from app.models.wallet import Wallet
from app.core.config import settings
from app.services.reward_program import program_ledger_type
from app.services.wallet_balance import spendable_wallet_balance
from app.services.funding_allocation import assert_wallet_funding_invariants


def reward_money(value: Decimal | float | int | None) -> Decimal:
    return Decimal(str(value or 0)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


def period_key(value: datetime | None = None) -> str:
    current = value or datetime.now(timezone.utc)
    if current.tzinfo is None:
        current = current.replace(tzinfo=timezone.utc)
    try:
        business_timezone = ZoneInfo(settings.REWARD_TIMEZONE)
    except ZoneInfoNotFoundError:
        business_timezone = timezone.utc
    return current.astimezone(business_timezone).strftime("%Y-%m")


def create_reward_accrual(
    db: Session,
    *,
    program_code: str,
    policy_version: str,
    beneficiary_user_id: int,
    source_type: str,
    source_id: int,
    order_id: int | None,
    order_renewal_id: int | None,
    asset_id: int | None,
    period: str,
    base_amount: Decimal,
    rate_bps: int,
    reward_amount: Decimal,
    policy_snapshot: dict,
    due_at: datetime,
    idempotency_key: str,
) -> tuple[RewardAccrual, bool]:
    existing = db.query(RewardAccrual).filter(
        RewardAccrual.idempotency_key == idempotency_key,
    ).first()
    if existing:
        return existing, False
    accrual = RewardAccrual(
        program_code=program_code,
        policy_version=policy_version,
        beneficiary_user_id=beneficiary_user_id,
        source_type=source_type,
        source_id=source_id,
        order_id=order_id,
        order_renewal_id=order_renewal_id,
        asset_id=asset_id,
        period_key=period,
        base_amount=Decimal(str(base_amount)),
        rate_bps=int(rate_bps),
        reward_amount=reward_money(reward_amount),
        policy_snapshot=policy_snapshot,
        due_at=due_at,
        status="pending",
        idempotency_key=idempotency_key,
    )
    db.add(accrual)
    db.flush()
    return accrual, True


def settle_reward_accrual(accrual_id: int, db: Session) -> Decimal:
    """Credit one accrual exactly once inside the caller transaction."""
    accrual = db.query(RewardAccrual).filter(
        RewardAccrual.id == accrual_id,
    ).with_for_update().first()
    if not accrual or accrual.status in ("settled", "forfeited"):
        return Decimal("0")

    existing = db.query(Ledger).filter(
        Ledger.ref_reward_accrual_id == accrual.id,
    ).first()
    if existing:
        accrual.status = "settled"
        accrual.settled_ledger_id = existing.id
        accrual.settled_at = existing.created_at or datetime.now(timezone.utc)
        db.flush()
        return Decimal("0")

    amount = reward_money(accrual.reward_amount)
    if amount <= 0:
        accrual.status = "settled"
        accrual.settled_at = datetime.now(timezone.utc)
        db.flush()
        return Decimal("0")

    wallet = db.query(Wallet).filter(
        Wallet.user_id == accrual.beneficiary_user_id,
    ).with_for_update().first()
    if wallet is None:
        return Decimal("0")

    wallet.balance = Decimal(str(wallet.balance or 0)) + amount
    # Every versioned reward is promotional: spendable in-app, never
    # withdrawable and never a cash-backed invitation-commission base.
    wallet.promotional_balance = Decimal(str(wallet.promotional_balance or 0)) + amount
    remarks = {
        "consumer_purchase": f"购买到期返佣 计提#{accrual.id}",
        "supplier_sales": f"商家月度销售返佣 计提#{accrual.id}",
        "invite_first_order": f"邀请好友首单返利 计提#{accrual.id}",
        "invite_qualification_bonus": f"邀请好友达标奖励 计提#{accrual.id}",
        "invite_consumption_commission": f"邀请好友消费返佣 计提#{accrual.id}",
    }
    ledger = Ledger(
        user_id=accrual.beneficiary_user_id,
        wallet_id=wallet.id,
        type=program_ledger_type(accrual.program_code),
        direction="in",
        amount=amount,
        balance_after=spendable_wallet_balance(wallet, db),
        ref_order_id=accrual.order_id if accrual.order_renewal_id is None else None,
        # ``ledger.ref_order_renewal_id`` is reserved for the renewal debit
        # itself and is globally unique. Reward credits use their own durable
        # reference so a renewal can safely create both entries.
        ref_order_renewal_id=None,
        ref_reward_accrual_id=accrual.id,
        event_key=f"reward_accrual:{accrual.id}",
        remark=remarks.get(accrual.program_code, f"奖励计提#{accrual.id}"),
    )
    db.add(ledger)
    db.flush()
    assert_wallet_funding_invariants(wallet, db)
    accrual.status = "settled"
    accrual.settled_ledger_id = ledger.id
    accrual.settled_at = datetime.now(timezone.utc)
    db.flush()
    return amount
