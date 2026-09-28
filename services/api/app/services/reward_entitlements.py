"""Independent, versioned consumer and supplier reward programs.

Only rows in ``reward_accruals`` are visible to these writers. Legacy asset
flags and legacy reward ledger types are deliberately ignored.
"""

from datetime import datetime, timezone
from decimal import Decimal
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.core.config import settings
from app.db.session import SessionLocal
from app.models.asset import Asset
from app.models.invite import InviteRecord
from app.models.order import Order
from app.models.order_renewal import OrderRenewal
from app.models.product import Product
from app.models.reward_accrual import RewardAccrual
from app.models.supplier import Supplier
from app.models.wallet import Wallet
from app.services.reward_accrual import (
    create_reward_accrual,
    period_key,
    reward_money,
    settle_reward_accrual,
)
from app.services.reward_program import (
    PROGRAM_CONSUMER,
    PROGRAM_INVITE,
    PROGRAM_INVITE_COMMISSION,
    PROGRAM_INVITE_QUALIFICATION,
    PROGRAM_SUPPLIER,
    program_enabled,
)


CONSUMER_POLICY_VERSION = "consumer-monthly-tier-v1"
CONSUMER_TIERS = (
    (Decimal("10000"), 300),
    (Decimal("50000"), 500),
    (Decimal("100000"), 700),
    (None, 1000),
)
CONSUMER_MONTHLY_CAP = Decimal("20000")

SUPPLIER_POLICY_VERSION = "supplier-monthly-target-v1"
SUPPLIER_TIERS = (
    (Decimal("10000"), 500),
    (Decimal("50000"), 800),
    (Decimal("100000"), 1100),
    (Decimal("200000"), 1300),
    (None, 1500),
)
SUPPLIER_MONTHLY_CAP = Decimal("50000")

INVITE_POLICY_VERSION = "invite-first-order-v1"


def _rate_bps(total: Decimal, tiers: tuple[tuple[Decimal | None, int], ...]) -> int:
    for threshold, rate in tiers:
        if threshold is None or total <= threshold:
            return rate
    return tiers[-1][1]


def _period_total(
    db: Session,
    *,
    program_code: str,
    beneficiary_user_id: int,
    period: str,
    column,
    statuses: tuple[str, ...] = ("pending", "settled"),
) -> Decimal:
    total = db.query(func.coalesce(func.sum(column), 0)).filter(
        RewardAccrual.program_code == program_code,
        RewardAccrual.beneficiary_user_id == beneficiary_user_id,
        RewardAccrual.period_key == period,
        RewardAccrual.status.in_(statuses),
    ).scalar()
    return reward_money(total)


def _lock_reward_period(beneficiary_user_id: int, db: Session) -> None:
    """Serialize monthly cap/target calculations for one beneficiary.

    All normal users own one wallet row. Reusing that durable row as the lock
    avoids introducing a database-specific advisory-lock dependency while
    keeping reward calculation in the caller's order transaction.
    """
    db.query(Wallet.id).filter(
        Wallet.user_id == beneficiary_user_id,
    ).with_for_update().first()


def _tier_rows(tiers: tuple[tuple[Decimal | None, int], ...]) -> list[dict]:
    return [
        {
            "max_month_spent": float(threshold) if threshold is not None else None,
            "rate": rate // 100,
            "rate_bps": rate,
        }
        for threshold, rate in tiers
    ]


def _business_period_bounds(period: str) -> tuple[datetime, datetime]:
    year_text, month_text = period.split("-", 1)
    year, month = int(year_text), int(month_text)
    try:
        business_timezone = ZoneInfo(settings.REWARD_TIMEZONE)
    except ZoneInfoNotFoundError:
        business_timezone = timezone.utc
    start_local = datetime(year, month, 1, tzinfo=business_timezone)
    if month == 12:
        end_local = datetime(year + 1, 1, 1, tzinfo=business_timezone)
    else:
        end_local = datetime(year, month + 1, 1, tzinfo=business_timezone)
    # SQLAlchemy DateTime columns in the existing schema store naive UTC.
    return (
        start_local.astimezone(timezone.utc).replace(tzinfo=None),
        end_local.astimezone(timezone.utc).replace(tzinfo=None),
    )


def _settled_in_period_total(
    db: Session,
    *,
    program_code: str,
    beneficiary_user_id: int,
    period: str,
) -> Decimal:
    start, end = _business_period_bounds(period)
    total = db.query(func.coalesce(func.sum(RewardAccrual.reward_amount), 0)).filter(
        RewardAccrual.program_code == program_code,
        RewardAccrual.beneficiary_user_id == beneficiary_user_id,
        RewardAccrual.status == "settled",
        RewardAccrual.settled_at >= start,
        RewardAccrual.settled_at < end,
    ).scalar()
    return reward_money(total)


def _pending_total(db: Session, *, program_code: str, beneficiary_user_id: int) -> Decimal:
    total = db.query(func.coalesce(func.sum(RewardAccrual.reward_amount), 0)).filter(
        RewardAccrual.program_code == program_code,
        RewardAccrual.beneficiary_user_id == beneficiary_user_id,
        RewardAccrual.status == "pending",
    ).scalar()
    return reward_money(total)


def _next_tier_hint(total: Decimal, tiers: tuple[tuple[Decimal | None, int], ...], noun: str) -> str:
    for threshold, rate in tiers:
        if threshold is not None and total <= threshold:
            next_rate = next(candidate for _, candidate in tiers if candidate > rate)
            # Tier upper bounds are inclusive, so one cent of a card-hour is
            # required when the running total sits exactly on the boundary.
            remaining = reward_money(max(Decimal("0.01"), threshold - total + Decimal("0.01")))
            remaining_text = format(remaining, "f").rstrip("0").rstrip(".")
            return f"再{noun} {remaining_text} 卡时可升至 {next_rate // 100}% 返佣"
    return f"已达最高返佣等级 {tiers[-1][1] // 100}%"


def consumer_quote(user_id: int, base_amount: Decimal, db: Session, event_at: datetime | None = None) -> dict:
    event = event_at or datetime.now(timezone.utc)
    period = period_key(event)
    base = reward_money(base_amount)
    spent_before = _period_total(
        db,
        program_code=PROGRAM_CONSUMER,
        beneficiary_user_id=user_id,
        period=period,
        column=RewardAccrual.base_amount,
    )
    projected = reward_money(spent_before + base)
    rate_bps = _rate_bps(projected, CONSUMER_TIERS)
    gross = reward_money(base * Decimal(rate_bps) / Decimal("10000"))
    cap_used = _period_total(
        db,
        program_code=PROGRAM_CONSUMER,
        beneficiary_user_id=user_id,
        period=period,
        column=RewardAccrual.reward_amount,
    )
    cap_remaining = max(Decimal("0"), CONSUMER_MONTHLY_CAP - cap_used)
    return {
        "period_key": period,
        "base_amount": base,
        "month_spent_before": spent_before,
        "projected_month_spent": projected,
        "rate_bps": rate_bps,
        "gross_reward": gross,
        "cap_used_before": cap_used,
        "cap_remaining_before": cap_remaining,
        "reward_amount": min(gross, cap_remaining),
    }


def _defer_consumer_order(order_id: int, due_at: datetime, db: Session) -> None:
    db.query(RewardAccrual).filter(
        RewardAccrual.program_code == PROGRAM_CONSUMER,
        RewardAccrual.order_id == order_id,
        RewardAccrual.status == "pending",
    ).update({RewardAccrual.due_at: due_at}, synchronize_session=False)


def _create_consumer_accrual(
    order: Order,
    asset: Asset,
    *,
    source_type: str,
    source_id: int,
    order_renewal_id: int | None,
    base_amount: Decimal,
    event_at: datetime,
    db: Session,
) -> RewardAccrual | None:
    if not program_enabled(PROGRAM_CONSUMER):
        return None
    if order.purchase_type != "usage" or order.status not in ("completed", "running"):
        return None
    if asset.end_at is None:
        return None
    # Event identity must survive policy upgrades.  ``policy_version`` belongs
    # in the immutable snapshot, never in the business idempotency key.
    key = f"reward:{PROGRAM_CONSUMER}:{source_type}:{source_id}"
    existing = db.query(RewardAccrual).filter(RewardAccrual.idempotency_key == key).first()
    if existing:
        return existing
    _lock_reward_period(order.user_id, db)
    # Re-check after acquiring the beneficiary lock so two retries cannot both
    # reserve the same cap allocation.
    existing = db.query(RewardAccrual).filter(RewardAccrual.idempotency_key == key).first()
    if existing:
        return existing
    quote = consumer_quote(order.user_id, base_amount, db, event_at)
    accrual, _ = create_reward_accrual(
        db,
        program_code=PROGRAM_CONSUMER,
        policy_version=CONSUMER_POLICY_VERSION,
        beneficiary_user_id=order.user_id,
        source_type=source_type,
        source_id=source_id,
        order_id=order.id,
        order_renewal_id=order_renewal_id,
        asset_id=asset.id,
        period=quote["period_key"],
        base_amount=quote["base_amount"],
        rate_bps=quote["rate_bps"],
        reward_amount=quote["reward_amount"],
        policy_snapshot={
            "tiers": _tier_rows(CONSUMER_TIERS),
            "monthly_cap": float(CONSUMER_MONTHLY_CAP),
            "month_spent_before": float(quote["month_spent_before"]),
            "projected_month_spent": float(quote["projected_month_spent"]),
            "gross_reward": float(quote["gross_reward"]),
            "cap_used_before": float(quote["cap_used_before"]),
        },
        due_at=asset.end_at,
        idempotency_key=key,
    )
    _defer_consumer_order(order.id, asset.end_at, db)
    return accrual


def create_consumer_order_accrual(order: Order, asset: Asset, event_at: datetime, db: Session):
    # Coupon value is a platform subsidy, not buyer spend. Do not stack a
    # purchase rebate on the discounted portion of the same order.
    eligible_spend = max(
        Decimal("0"),
        Decimal(str(order.amount or 0)) - Decimal(str(order.coupon_discount or 0)),
    )
    return _create_consumer_accrual(
        order,
        asset,
        source_type="order",
        source_id=order.id,
        order_renewal_id=None,
        base_amount=eligible_spend,
        event_at=event_at,
        db=db,
    )


def create_consumer_renewal_accrual(
    order: Order,
    renewal: OrderRenewal,
    asset: Asset,
    event_at: datetime,
    db: Session,
):
    return _create_consumer_accrual(
        order,
        asset,
        source_type="renewal",
        source_id=renewal.id,
        order_renewal_id=renewal.id,
        base_amount=Decimal(str(renewal.amount or 0)),
        event_at=event_at,
        db=db,
    )


def _supplier_for_order(order: Order, db: Session) -> Supplier | None:
    product = db.query(Product).filter(Product.id == order.product_id).first()
    if not product or not product.supplier_id:
        return None
    supplier = db.query(Supplier).filter(
        Supplier.id == product.supplier_id,
        Supplier.status == "approved",
    ).first()
    if not supplier or supplier.user_id == order.user_id:
        return None
    return supplier


def _create_supplier_accrual(
    order: Order,
    *,
    source_type: str,
    source_id: int,
    order_renewal_id: int | None,
    base_amount: Decimal,
    event_at: datetime,
    db: Session,
) -> RewardAccrual | None:
    if not program_enabled(PROGRAM_SUPPLIER) or order.status not in ("completed", "running"):
        return None
    supplier = _supplier_for_order(order, db)
    if supplier is None:
        return None
    key = f"reward:{PROGRAM_SUPPLIER}:{source_type}:{source_id}"
    existing = db.query(RewardAccrual).filter(RewardAccrual.idempotency_key == key).first()
    if existing:
        return existing
    _lock_reward_period(supplier.user_id, db)
    existing = db.query(RewardAccrual).filter(RewardAccrual.idempotency_key == key).first()
    if existing:
        return existing
    period = period_key(event_at)
    sales_before = _period_total(
        db,
        program_code=PROGRAM_SUPPLIER,
        beneficiary_user_id=supplier.user_id,
        period=period,
        column=RewardAccrual.base_amount,
    )
    projected_sales = reward_money(sales_before + Decimal(str(base_amount)))
    rate_bps = _rate_bps(projected_sales, SUPPLIER_TIERS)
    monthly_target = min(
        reward_money(projected_sales * Decimal(rate_bps) / Decimal("10000")),
        SUPPLIER_MONTHLY_CAP,
    )
    granted_before = _period_total(
        db,
        program_code=PROGRAM_SUPPLIER,
        beneficiary_user_id=supplier.user_id,
        period=period,
        column=RewardAccrual.reward_amount,
    )
    increment = max(Decimal("0"), monthly_target - granted_before)
    accrual, _ = create_reward_accrual(
        db,
        program_code=PROGRAM_SUPPLIER,
        policy_version=SUPPLIER_POLICY_VERSION,
        beneficiary_user_id=supplier.user_id,
        source_type=source_type,
        source_id=source_id,
        order_id=order.id,
        order_renewal_id=order_renewal_id,
        asset_id=None,
        period=period,
        base_amount=Decimal(str(base_amount)),
        rate_bps=rate_bps,
        reward_amount=increment,
        policy_snapshot={
            "tiers": _tier_rows(SUPPLIER_TIERS),
            "monthly_cap": float(SUPPLIER_MONTHLY_CAP),
            "sales_before": float(sales_before),
            "projected_sales": float(projected_sales),
            "monthly_target": float(monthly_target),
            "granted_before": float(granted_before),
        },
        due_at=event_at,
        idempotency_key=key,
    )
    if settings.REWARD_SETTLEMENT_ENABLED:
        settle_reward_accrual(accrual.id, db)
    return accrual


def create_supplier_order_accrual(order: Order, event_at: datetime, db: Session):
    return _create_supplier_accrual(
        order,
        source_type="order",
        source_id=order.id,
        order_renewal_id=None,
        base_amount=Decimal(str(order.amount or 0)),
        event_at=event_at,
        db=db,
    )


def create_supplier_renewal_accrual(
    order: Order,
    renewal: OrderRenewal,
    event_at: datetime,
    db: Session,
):
    return _create_supplier_accrual(
        order,
        source_type="renewal",
        source_id=renewal.id,
        order_renewal_id=renewal.id,
        base_amount=Decimal(str(renewal.amount or 0)),
        event_at=event_at,
        db=db,
    )


def create_invite_accrual(
    *,
    beneficiary_user_id: int,
    order: Order,
    rate_bps: int,
    event_at: datetime,
    db: Session,
) -> RewardAccrual | None:
    if not program_enabled(PROGRAM_INVITE):
        return None
    key = f"reward:{PROGRAM_INVITE}:order:{order.id}"
    existing = db.query(RewardAccrual).filter(RewardAccrual.idempotency_key == key).first()
    if existing:
        return existing
    from app.services.account_lifecycle import try_lock_active_user
    if not try_lock_active_user(db, beneficiary_user_id):
        return None
    reward = reward_money(Decimal(str(order.amount or 0)) * Decimal(rate_bps) / Decimal("10000"))
    accrual, _ = create_reward_accrual(
        db,
        program_code=PROGRAM_INVITE,
        policy_version=INVITE_POLICY_VERSION,
        beneficiary_user_id=beneficiary_user_id,
        source_type="order",
        source_id=order.id,
        order_id=order.id,
        order_renewal_id=None,
        asset_id=None,
        period=period_key(event_at),
        base_amount=Decimal(str(order.amount or 0)),
        rate_bps=rate_bps,
        reward_amount=reward,
        policy_snapshot={"rate_bps": rate_bps, "first_confirmed_usage_order": True},
        due_at=event_at,
        idempotency_key=key,
    )
    if settings.REWARD_SETTLEMENT_ENABLED:
        settle_reward_accrual(accrual.id, db)
    return accrual


def settle_reward_entitlements(db: Session, now: datetime | None = None) -> int:
    if not settings.REWARD_SETTLEMENT_ENABLED:
        return 0
    current = now or datetime.now(timezone.utc)
    due = db.query(RewardAccrual).filter(
        RewardAccrual.program_code.in_((
            PROGRAM_CONSUMER,
            PROGRAM_SUPPLIER,
            PROGRAM_INVITE,
            PROGRAM_INVITE_QUALIFICATION,
            PROGRAM_INVITE_COMMISSION,
        )),
        RewardAccrual.status == "pending",
        RewardAccrual.due_at <= current,
    ).order_by(RewardAccrual.id.asc()).all()
    settled = 0
    for accrual in due:
        if accrual.program_code == PROGRAM_CONSUMER:
            # Renewal updates the same asset before deferring all pending
            # accruals. Locking it here gives expiry settlement a deterministic
            # order against a concurrent renewal at the deadline.
            asset = db.query(Asset).filter(
                Asset.id == accrual.asset_id,
            ).with_for_update().first()
            order = db.query(Order).filter(Order.id == accrual.order_id).first()
            if not asset or not order or order.status == "canceled":
                accrual.status = "forfeited"
                continue
            if asset.purchase_type != "usage" or asset.status == "sold":
                accrual.status = "forfeited"
                continue
            if asset.end_at is None:
                continue
            asset_end = asset.end_at
            if asset_end.tzinfo is None and current.tzinfo is not None:
                asset_end = asset_end.replace(tzinfo=timezone.utc)
            if asset_end > current:
                accrual.due_at = asset.end_at
                continue
        before = accrual.status
        settle_reward_accrual(accrual.id, db)
        db.refresh(accrual)
        if accrual.program_code == PROGRAM_INVITE and accrual.status == "settled":
            order = db.query(Order).filter(Order.id == accrual.order_id).first()
            record = db.query(InviteRecord).filter(
                InviteRecord.invitee_id == order.user_id,
            ).first() if order else None
            if record:
                record.status = "rewarded"
                record.reward_amount = float(accrual.reward_amount)
                record.ordered_at = order.start_at
                record.rewarded_at = accrual.settled_at
                record.last_modified_platform = "system"
        if before == "pending" and accrual.status == "settled":
            settled += 1
    db.flush()
    return settled


def settle_reward_entitlements_job() -> int:
    db: Session = SessionLocal()
    try:
        count = settle_reward_entitlements(db)
        db.commit()
        return count
    except Exception as exc:
        db.rollback()
        print(f"[settle_reward_entitlements] error: {exc}")
        return 0
    finally:
        db.close()


def get_consumer_summary(user_id: int, db: Session) -> dict:
    enabled = program_enabled(PROGRAM_CONSUMER)
    period = period_key()
    spent = _period_total(
        db,
        program_code=PROGRAM_CONSUMER,
        beneficiary_user_id=user_id,
        period=period,
        column=RewardAccrual.base_amount,
    )
    entitled = _period_total(
        db,
        program_code=PROGRAM_CONSUMER,
        beneficiary_user_id=user_id,
        period=period,
        column=RewardAccrual.reward_amount,
    )
    settled = _settled_in_period_total(
        db, program_code=PROGRAM_CONSUMER, beneficiary_user_id=user_id, period=period,
    )
    pending = _pending_total(db, program_code=PROGRAM_CONSUMER, beneficiary_user_id=user_id)
    rate = _rate_bps(spent, CONSUMER_TIERS)
    return {
        "program_code": "consumer_purchase_rebate",
        "policy_version": CONSUMER_POLICY_VERSION,
        "period_key": period,
        "month_spent": float(spent),
        "month_rebated": float(settled),
        "month_entitled": float(entitled),
        "current_rate": rate // 100,
        "minimum_order_amount": 0.0,
        "tiers": _tier_rows(CONSUMER_TIERS),
        "next_tier_hint": _next_tier_hint(spent, CONSUMER_TIERS, "购买") if enabled else "返佣计划当前未开启",
        "pending_rebate": float(pending),
        "monthly_cap": float(CONSUMER_MONTHLY_CAP),
        "cap_used": float(entitled),
        "cap_remaining": float(max(Decimal("0"), CONSUMER_MONTHLY_CAP - entitled)),
        "rewards_enabled": enabled,
        "reward_mode": "live" if enabled else "disabled",
    }


def get_supplier_summary(supplier_user_id: int, db: Session) -> dict:
    enabled = program_enabled(PROGRAM_SUPPLIER)
    period = period_key()
    sales = _period_total(
        db,
        program_code=PROGRAM_SUPPLIER,
        beneficiary_user_id=supplier_user_id,
        period=period,
        column=RewardAccrual.base_amount,
    )
    entitled = _period_total(
        db,
        program_code=PROGRAM_SUPPLIER,
        beneficiary_user_id=supplier_user_id,
        period=period,
        column=RewardAccrual.reward_amount,
    )
    settled = _settled_in_period_total(
        db, program_code=PROGRAM_SUPPLIER, beneficiary_user_id=supplier_user_id, period=period,
    )
    pending = _pending_total(db, program_code=PROGRAM_SUPPLIER, beneficiary_user_id=supplier_user_id)
    rate = _rate_bps(sales, SUPPLIER_TIERS)
    target = min(reward_money(sales * Decimal(rate) / Decimal("10000")), SUPPLIER_MONTHLY_CAP)
    return {
        "program_code": "supplier_sales_rebate",
        "policy_version": SUPPLIER_POLICY_VERSION,
        "period_key": period,
        "month_sales": float(sales),
        "month_rebated": float(settled),
        "month_entitled": float(entitled),
        "pending_rebate": float(pending),
        "current_rate": rate // 100,
        "tiers": _tier_rows(SUPPLIER_TIERS),
        "monthly_target": float(target),
        "est_total_rebate": float(target),
        "next_tier_hint": _next_tier_hint(sales, SUPPLIER_TIERS, "销售") if enabled else "返佣计划当前未开启",
        "monthly_cap": float(SUPPLIER_MONTHLY_CAP),
        "cap_used": float(entitled),
        "cap_remaining": float(max(Decimal("0"), SUPPLIER_MONTHLY_CAP - entitled)),
        "rebate_basis_percent": 100,
        "platform_service_fee_percent": int(settings.MERCHANT_SERVICE_FEE_BPS) / 100,
        # Deprecated compatibility field. It described the rebate basis, not
        # the commercial platform fee; new clients must use the two fields above.
        "service_fee_rate": 100,
        "rewards_enabled": enabled,
        "reward_mode": "live" if enabled else "disabled",
    }


def _summarize_asset_consumer_reward(rows: list[RewardAccrual]) -> dict | None:
    if not rows:
        return None
    eligible_rows = [row for row in rows if row.status != "forfeited"]
    pending = reward_money(sum((row.reward_amount for row in eligible_rows if row.status == "pending"), Decimal("0")))
    settled = reward_money(sum((row.reward_amount for row in eligible_rows if row.status == "settled"), Decimal("0")))
    total = reward_money(sum((row.reward_amount for row in eligible_rows), Decimal("0")))
    if not eligible_rows:
        status = "forfeited"
    elif any(row.status == "pending" for row in eligible_rows):
        status = "pending"
    else:
        # A valid zero-value row can occur after the monthly cap is exhausted.
        status = "rewarded"
    return {
        "rebate_status": status,
        "rebate_amount": float(total),
        "pending_rebate": float(pending),
        "settled_rebate": float(settled),
        "policy_versions": sorted({row.policy_version for row in rows}),
    }


def get_assets_consumer_rewards(asset_ids: list[int], db: Session) -> dict[int, dict]:
    """Return audited purchase-rebate facts for a group of assets in one query."""
    normalized_ids = sorted({int(asset_id) for asset_id in asset_ids if int(asset_id) > 0})
    if not normalized_ids:
        return {}
    rows = db.query(RewardAccrual).filter(
        RewardAccrual.program_code == PROGRAM_CONSUMER,
        RewardAccrual.asset_id.in_(normalized_ids),
    ).order_by(RewardAccrual.asset_id.asc(), RewardAccrual.id.asc()).all()
    grouped: dict[int, list[RewardAccrual]] = {}
    for row in rows:
        if row.asset_id is None:
            continue
        grouped.setdefault(int(row.asset_id), []).append(row)
    return {
        asset_id: summary
        for asset_id, asset_rows in grouped.items()
        if (summary := _summarize_asset_consumer_reward(asset_rows)) is not None
    }


def get_asset_consumer_reward(asset_id: int, db: Session) -> dict | None:
    return get_assets_consumer_rewards([asset_id], db).get(int(asset_id))
