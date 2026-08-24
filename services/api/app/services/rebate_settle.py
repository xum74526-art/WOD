"""Consumer rebate calculation and expiry settlement.

Only confirmed usage orders participate. In-app rewards are card-hours
that can be reused for eligible purchases, never fiat and never withdrawable while
the payment service is disabled.
"""

from datetime import date, datetime, time, timezone
from decimal import Decimal, ROUND_HALF_UP

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.db.session import SessionLocal
from app.models.asset import Asset
from app.models.ledger import Ledger
from app.models.order import Order
from app.models.wallet import Wallet
from app.services.reward_program import (
    active_reward_ledger_types,
    reward_ledger_type,
    reward_mode,
    reward_program_enabled,
)


MONTHLY_TIERS = [
    (10_000, Decimal("0.03")),
    (50_000, Decimal("0.05")),
    (100_000, Decimal("0.07")),
    (float("inf"), Decimal("0.10")),
]

MONTHLY_REBATE_CAP = Decimal("500")
MIN_ORDER_AMOUNT = Decimal("10")


def _money(value: Decimal | float | int | None) -> Decimal:
    return Decimal(str(value or 0)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


def _month_start(value: date | None = None) -> datetime:
    current = value or date.today()
    return datetime.combine(current.replace(day=1), time.min)


def _get_rebate_rate(monthly_spent: float | Decimal) -> Decimal:
    spent = Decimal(str(monthly_spent or 0))
    for threshold, rate in MONTHLY_TIERS:
        if threshold == float("inf") or spent <= Decimal(str(threshold)):
            return rate
    return Decimal("0.10")


def _get_month_spent(user_id: int, db: Session, month: date | None = None) -> Decimal:
    """Completed usage-order card-hours for the month, including pending rebates."""
    total = db.query(func.coalesce(func.sum(Order.amount), 0)).filter(
        Order.user_id == user_id,
        Order.purchase_type == "usage",
        Order.status.in_(["completed", "running"]),
        Order.start_at >= _month_start(month),
    ).scalar()
    return _money(total)


def _get_month_rebated(user_id: int, db: Session, month: date | None = None) -> Decimal:
    ledger_types = active_reward_ledger_types("consumer")
    if not ledger_types:
        return Decimal("0")
    total = db.query(func.coalesce(func.sum(Ledger.amount), 0)).filter(
        Ledger.user_id == user_id,
        Ledger.type.in_(ledger_types),
        Ledger.direction == "in",
        Ledger.created_at >= _month_start(month),
    ).scalar()
    return _money(total)


def estimate_completed_order_rebate(order: Order | None, db: Session) -> Decimal:
    """Return a deterministic estimate from an actual confirmed usage order."""
    if not order or not reward_program_enabled() or order.purchase_type != "usage":
        return Decimal("0")
    if order.status not in ("completed", "running"):
        return Decimal("0")
    amount = _money(order.amount)
    if amount < MIN_ORDER_AMOUNT:
        return Decimal("0")
    db.flush()
    rate = _get_rebate_rate(_get_month_spent(order.user_id, db))
    return _money(amount * rate)


def _asset_total_value(asset: Asset) -> Decimal:
    return _money(Decimal(str(asset.value or 0)) * max(int(asset.quantity or 1), 1))


def settle_rebates(db: Session, now: datetime | None = None) -> int:
    """Settle due assets in the caller transaction; safe to run repeatedly."""
    if not reward_program_enabled():
        return 0
    current = now or datetime.now(timezone.utc)
    ledger_type = reward_ledger_type("consumer")

    sold_assets = db.query(Asset).filter(
        Asset.status == "sold",
        Asset.rebate_status == "pending",
    ).all()
    for asset in sold_assets:
        asset.rebate_status = "forfeited"

    ineligible_assets = db.query(Asset).filter(
        Asset.purchase_type != "usage",
        Asset.rebate_status == "pending",
    ).all()
    for asset in ineligible_assets:
        asset.rebate_status = "forfeited"

    due_assets = db.query(Asset).filter(
        Asset.status.in_(["active", "expired"]),
        Asset.purchase_type == "usage",
        Asset.rebate_status == "pending",
        Asset.end_at.isnot(None),
    ).all()

    rewarded_count = 0
    for asset in due_assets:
        end_at = asset.end_at
        if end_at is None:
            continue
        end = end_at.replace(tzinfo=timezone.utc) if end_at.tzinfo is None else end_at
        if end > current:
            continue
        asset.status = "expired"

        existing = None
        if asset.order_id:
            existing = db.query(Ledger).filter(
                Ledger.user_id == asset.user_id,
                Ledger.type == ledger_type,
                Ledger.ref_order_id == asset.order_id,
            ).first()
        if existing:
            asset.rebate_status = "rewarded"
            asset.rebate_amount = float(existing.amount)
            continue

        value = _asset_total_value(asset)
        if value < MIN_ORDER_AMOUNT:
            asset.rebate_status = "rewarded"
            asset.rebate_amount = 0
            continue

        month_rebated = _get_month_rebated(asset.user_id, db)
        remaining = max(Decimal("0"), MONTHLY_REBATE_CAP - month_rebated)
        if remaining <= 0:
            continue

        expected = _money(asset.rebate_amount)
        if expected <= 0:
            order = db.query(Order).filter(Order.id == asset.order_id).first() if asset.order_id else None
            expected = estimate_completed_order_rebate(order, db) if order else _money(value * _get_rebate_rate(0))
        rebate = min(expected, remaining)

        wallet = db.query(Wallet).filter(Wallet.user_id == asset.user_id).with_for_update().first()
        if wallet is None:
            continue
        if rebate > 0:
            wallet.balance = Decimal(str(wallet.balance or 0)) + rebate
            db.add(Ledger(
                user_id=asset.user_id,
                wallet_id=wallet.id,
                type=ledger_type,
                direction="in",
                amount=rebate,
                balance_after=wallet.balance,
                ref_order_id=asset.order_id,
                remark=f"消费返佣 资产#{asset.id}",
            ))
        asset.rebate_status = "rewarded"
        asset.rebate_amount = float(rebate)
        rewarded_count += 1

    db.flush()
    return rewarded_count


def settle_rebate() -> int:
    """Scheduled wrapper with one atomic commit."""
    if not reward_program_enabled():
        return 0
    db: Session = SessionLocal()
    try:
        count = settle_rebates(db)
        db.commit()
        return count
    except Exception as exc:
        db.rollback()
        print(f"[settle_rebate] error: {exc}")
        return 0
    finally:
        db.close()


def get_rebate_summary(user_id: int, db: Session) -> dict:
    enabled = reward_program_enabled()
    month_spent = _get_month_spent(user_id, db) if enabled else Decimal("0")
    month_rebated = _get_month_rebated(user_id, db) if enabled else Decimal("0")
    current_rate = _get_rebate_rate(month_spent)

    next_hint = "返佣计划当前未开启"
    if enabled:
        for threshold, rate in MONTHLY_TIERS:
            if threshold == float("inf") or month_spent <= Decimal(str(threshold)):
                if rate < Decimal("0.10"):
                    next_rate = next(candidate for _, candidate in MONTHLY_TIERS if candidate > rate)
                    next_hint = f"再消费 {int(Decimal(str(threshold)) - month_spent)} 卡时可升至 {int(next_rate * 100)}% 返佣"
                else:
                    next_hint = "已达最高返佣等级 10%"
                break

    pending_total = Decimal("0")
    if enabled:
        pending_assets = db.query(Asset).filter(
            Asset.user_id == user_id,
            Asset.purchase_type == "usage",
            Asset.rebate_status == "pending",
            Asset.status.in_(["active", "expired"]),
        ).all()
        pending_total = sum((_money(asset.rebate_amount) for asset in pending_assets), Decimal("0"))

    return {
        "month_spent": float(_money(month_spent)),
        "month_rebated": float(_money(month_rebated)),
        "current_rate": int(current_rate * 100),
        "minimum_order_amount": float(MIN_ORDER_AMOUNT),
        "tiers": [
            {
                "max_month_spent": None if threshold == float("inf") else float(threshold),
                "rate": int(rate * 100),
            }
            for threshold, rate in MONTHLY_TIERS
        ],
        "next_tier_hint": next_hint,
        "pending_rebate": float(_money(pending_total)),
        "monthly_cap": float(MONTHLY_REBATE_CAP),
        "rewards_enabled": enabled,
        "reward_mode": reward_mode(),
    }


if __name__ == "__main__":
    settle_rebate()
