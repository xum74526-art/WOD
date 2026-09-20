"""Order/payment lifecycle processing with bounded reserved-fund deadlines."""

from datetime import datetime, timedelta, timezone

from sqlalchemy.orm import Session

from app.core.config import settings
from app.db.session import SessionLocal
from app.models.asset import Asset
from app.models.order import Order
from app.models.product import Product
from app.routers.order import _complete_reserved_order, _refund_reserved_order
from app.services.market_freshness import product_market_source
from app.services.qixiangpay import expire_pending_payment_orders


ORDER_LIFECYCLE_POLICY_VERSION = "reserved-v1"


def _utc_naive(value: datetime | None = None) -> datetime:
    current = value or datetime.now(timezone.utc)
    if current.tzinfo is None:
        return current
    return current.astimezone(timezone.utc).replace(tzinfo=None)


def _restore_expired_order_stock(order: Order, db: Session, now: datetime) -> bool:
    changed = db.query(Order).filter(
        Order.id == order.id,
        Order.status.in_(("completed", "running")),
        Order.lifecycle_policy_version == ORDER_LIFECYCLE_POLICY_VERSION,
        Order.end_at.isnot(None),
        Order.end_at <= now,
        Order.stock_released_at.is_(None),
    ).update({
        Order.status: "done",
        Order.stock_released_at: now,
        Order.last_modified_platform: "system",
    }, synchronize_session=False)
    if changed != 1:
        return False
    product = db.query(Product).filter(Product.id == order.product_id).with_for_update().first()
    if product:
        restored = max(int(product.stock or 0), 0) + max(int(order.quantity or 1), 1)
        if product_market_source(product) == "kai" and product.platform_stock_cap is not None:
            restored = min(restored, max(int(product.platform_stock_cap), 0))
        product.stock = restored
    db.query(Asset).filter(
        Asset.order_id == order.id,
        Asset.status == "active",
    ).update({Asset.status: "expired"}, synchronize_session=False)
    return True


def process_order_lifecycle(
    db: Session,
    *,
    now: datetime | None = None,
) -> dict[str, int]:
    """Process lifecycle changes in the caller transaction.

    Historical pending rows receive a fresh full SLA window on their first run;
    they are never silently auto-confirmed or refunded immediately after an
    upgrade merely because their old schema had no deadline column.
    """

    current = _utc_naive(now)
    delivery_hours = max(int(settings.ORDER_DELIVERY_TIMEOUT_HOURS), 1)
    confirmation_hours = max(int(settings.ORDER_CONFIRMATION_TIMEOUT_HOURS), 1)
    dispute_hours = max(int(settings.ORDER_DISPUTE_REVIEW_TIMEOUT_HOURS), 1)

    backfilled = 0
    if settings.ORDER_LEGACY_PENDING_MIGRATION_ENABLED:
        for order in db.query(Order).filter(
            Order.status == "paid",
            Order.delivery_due_at.is_(None),
        ).all():
            order.lifecycle_policy_version = ORDER_LIFECYCLE_POLICY_VERSION
            order.delivery_due_at = current + timedelta(hours=delivery_hours)
            backfilled += 1
        for order in db.query(Order).filter(
            Order.status == "delivering",
            Order.confirmation_due_at.is_(None),
        ).all():
            order.lifecycle_policy_version = ORDER_LIFECYCLE_POLICY_VERSION
            order.delivered_at = order.delivered_at or current
            order.confirmation_due_at = current + timedelta(hours=confirmation_hours)
            backfilled += 1
        for order in db.query(Order).filter(
            Order.status == "disputed",
            Order.dispute_due_at.is_(None),
        ).all():
            order.lifecycle_policy_version = ORDER_LIFECYCLE_POLICY_VERSION
            order.dispute_due_at = current + timedelta(hours=dispute_hours)
            backfilled += 1
    db.flush()

    counts = {
        "deadline_backfilled": backfilled,
        "delivery_refunded": 0,
        "delivery_confirmed": 0,
        "dispute_refunded": 0,
        "expired": 0,
        "conflicts": 0,
    }

    due_delivery = db.query(Order).filter(
        Order.status == "paid",
        Order.delivery_due_at.isnot(None),
        Order.delivery_due_at <= current,
    ).all()
    for order in due_delivery:
        try:
            with db.begin_nested():
                if _refund_reserved_order(
                    order,
                    db,
                    platform="system",
                    reason="商家未在交付期限内完成交付，系统自动退款",
                    allowed_statuses=("paid",),
                ):
                    counts["delivery_refunded"] += 1
        except Exception:
            counts["conflicts"] += 1

    due_confirmation = db.query(Order).filter(
        Order.status == "delivering",
        Order.confirmation_due_at.isnot(None),
        Order.confirmation_due_at <= current,
    ).all()
    for order in due_confirmation:
        try:
            with db.begin_nested():
                if _complete_reserved_order(
                    order,
                    db,
                    platform="system",
                    allowed_statuses=("delivering",),
                ):
                    counts["delivery_confirmed"] += 1
        except Exception:
            counts["conflicts"] += 1

    due_disputes = db.query(Order).filter(
        Order.status == "disputed",
        Order.dispute_due_at.isnot(None),
        Order.dispute_due_at <= current,
    ).all()
    for order in due_disputes:
        try:
            with db.begin_nested():
                if _refund_reserved_order(
                    order,
                    db,
                    platform="system",
                    reason="争议超过平台处理时限，系统按买家保护规则退款",
                    allowed_statuses=("disputed",),
                ):
                    counts["dispute_refunded"] += 1
        except Exception:
            counts["conflicts"] += 1

    expired_orders = db.query(Order).filter(
        Order.status.in_(("completed", "running")),
        Order.lifecycle_policy_version == ORDER_LIFECYCLE_POLICY_VERSION,
        Order.end_at.isnot(None),
        Order.end_at <= current,
        Order.stock_released_at.is_(None),
    ).all()
    for order in expired_orders:
        try:
            with db.begin_nested():
                if _restore_expired_order_stock(order, db, current):
                    counts["expired"] += 1
        except Exception:
            counts["conflicts"] += 1

    db.flush()
    return counts


def expire_due() -> None:
    db: Session = SessionLocal()
    try:
        now = _utc_naive()
        counts = process_order_lifecycle(db, now=now)
        payment_orders = expire_pending_payment_orders(db, now=now)
        db.commit()
        if any(counts.values()) or payment_orders:
            print(f"[lifecycle] orders={counts}, expired_payments={payment_orders}")
    except Exception as exc:  # noqa: BLE001
        db.rollback()
        print(f"[lifecycle] error: {exc}")
    finally:
        db.close()
