"""Merchant sales rebate derived from confirmed ZTW merchant orders."""

from datetime import date, datetime, time
from decimal import Decimal, ROUND_HALF_UP

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.models.ledger import Ledger
from app.models.order import Order
from app.models.product import Product
from app.models.supplier import Supplier
from app.models.wallet import Wallet
from app.services.reward_program import (
    active_reward_ledger_types,
    reward_ledger_type,
    reward_mode,
    reward_program_enabled,
)


SUPPLIER_TIERS = [
    (10_000, Decimal("0.05")),
    (50_000, Decimal("0.08")),
    (100_000, Decimal("0.11")),
    (200_000, Decimal("0.13")),
    (float("inf"), Decimal("0.15")),
]

MONTHLY_CAP = Decimal("2000")
SERVICE_FEE_RATE = Decimal("0.10")


def _money(value) -> Decimal:
    return Decimal(str(value or 0)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


def _month_start(value: date | None = None) -> datetime:
    current = value or date.today()
    return datetime.combine(current.replace(day=1), time.min)


def _get_rebate_rate(monthly_sales: float | Decimal) -> Decimal:
    sales = Decimal(str(monthly_sales or 0))
    for threshold, rate in SUPPLIER_TIERS:
        if threshold == float("inf") or sales <= Decimal(str(threshold)):
            return rate
    return Decimal("0.15")


def _supplier_product_ids(supplier_user_id: int, db: Session) -> tuple[Supplier | None, list[int]]:
    supplier = db.query(Supplier).filter(
        Supplier.user_id == supplier_user_id,
        Supplier.status == "approved",
    ).first()
    if not supplier:
        return None, []
    ids = [row[0] for row in db.query(Product.id).filter(Product.supplier_id == supplier.id).all()]
    return supplier, ids


def _get_month_sales(supplier_user_id: int, db: Session, month: date | None = None) -> Decimal:
    _, product_ids = _supplier_product_ids(supplier_user_id, db)
    if not product_ids:
        return Decimal("0")
    total = db.query(func.coalesce(func.sum(Order.amount), 0)).filter(
        Order.product_id.in_(product_ids),
        Order.status.in_(["completed", "running"]),
        Order.start_at >= _month_start(month),
    ).scalar()
    return _money(total)


def _get_month_rebated(supplier_user_id: int, db: Session, month: date | None = None) -> Decimal:
    ledger_types = active_reward_ledger_types("supplier")
    if not ledger_types:
        return Decimal("0")
    total = db.query(func.coalesce(func.sum(Ledger.amount), 0)).filter(
        Ledger.user_id == supplier_user_id,
        Ledger.type.in_(ledger_types),
        Ledger.direction == "in",
        Ledger.created_at >= _month_start(month),
    ).scalar()
    return _money(total)


def process_supplier_rebate(supplier_user_id: int, order_id: int, db: Session) -> Decimal:
    """Add one merchant reward to the caller transaction, exactly once per order."""
    if not reward_program_enabled():
        return Decimal("0")
    supplier, product_ids = _supplier_product_ids(supplier_user_id, db)
    if not supplier or not product_ids:
        return Decimal("0")
    order = db.query(Order).filter(
        Order.id == order_id,
        Order.product_id.in_(product_ids),
        Order.status.in_(["completed", "running"]),
    ).first()
    if not order:
        return Decimal("0")
    if order.user_id == supplier_user_id:
        return Decimal("0")

    ledger_type = reward_ledger_type("supplier")
    existing = db.query(Ledger).filter(
        Ledger.user_id == supplier_user_id,
        Ledger.type == ledger_type,
        Ledger.ref_order_id == order.id,
    ).first()
    if existing:
        return Decimal("0")

    db.flush()
    month_rebated = _get_month_rebated(supplier_user_id, db)
    remaining = max(Decimal("0"), MONTHLY_CAP - month_rebated)
    if remaining <= 0:
        return Decimal("0")
    rate = _get_rebate_rate(_get_month_sales(supplier_user_id, db))
    service_fee = _money(Decimal(str(order.amount or 0)) * SERVICE_FEE_RATE)
    rebate = min(_money(service_fee * rate), remaining)
    if rebate <= 0:
        return Decimal("0")

    wallet = db.query(Wallet).filter(Wallet.user_id == supplier_user_id).with_for_update().first()
    if not wallet:
        return Decimal("0")
    wallet.balance = Decimal(str(wallet.balance or 0)) + rebate
    db.add(Ledger(
        user_id=supplier_user_id,
        wallet_id=wallet.id,
        type=ledger_type,
        direction="in",
        amount=rebate,
        balance_after=wallet.balance,
        ref_order_id=order.id,
        remark=f"商家销售返佣({int(rate * 100)}%)",
    ))
    db.flush()
    return rebate


def get_supplier_rebate_summary(supplier_user_id: int, db: Session) -> dict:
    enabled = reward_program_enabled()
    month_sales = _get_month_sales(supplier_user_id, db) if enabled else Decimal("0")
    month_rebated = _get_month_rebated(supplier_user_id, db) if enabled else Decimal("0")
    current_rate = _get_rebate_rate(month_sales)

    next_hint = "返佣计划当前未开启"
    if enabled:
        for threshold, rate in SUPPLIER_TIERS:
            if threshold == float("inf") or month_sales <= Decimal(str(threshold)):
                if rate < Decimal("0.15"):
                    next_rate = next(candidate for _, candidate in SUPPLIER_TIERS if candidate > rate)
                    next_hint = f"再销售 ¥{int(Decimal(str(threshold)) - month_sales)} 可升至 {int(next_rate * 100)}% 返佣"
                else:
                    next_hint = "已达最高返佣等级 15%"
                break

    est_total = _money(month_sales * SERVICE_FEE_RATE * current_rate) if enabled else Decimal("0")
    return {
        "month_sales": float(month_sales),
        "month_rebated": float(month_rebated),
        "current_rate": int(current_rate * 100),
        "est_total_rebate": float(est_total),
        "next_tier_hint": next_hint,
        "monthly_cap": float(MONTHLY_CAP),
        "service_fee_rate": int(SERVICE_FEE_RATE * 100),
        "rewards_enabled": enabled,
        "reward_mode": reward_mode(),
    }
