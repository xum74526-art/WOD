from __future__ import annotations

from datetime import datetime, timedelta, timezone

from sqlalchemy import or_
from sqlalchemy.orm import Session

from app.core.config import settings
from app.db.session import SessionLocal
from app.models.payment import PaymentOrder
from app.services.payment_operations import (
    record_payment_event,
    recover_stale_refund_submissions,
)
from app.services.qixiangpay import query_provider_and_reconcile
from app.utils.response import BizError


def utc_now() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


def reconcile_payment_orders(
    db: Session,
    *,
    now: datetime | None = None,
) -> dict[str, int]:
    counts = {"claimed": 0, "reconciled": 0, "errors": 0}
    if not settings.PAYMENT_RECONCILIATION_ENABLED:
        return counts
    current = now or utc_now()
    minimum_age = min(
        max(int(settings.PAYMENT_RECONCILIATION_MIN_AGE_SECONDS), 10),
        3600,
    )
    maximum_age = min(
        max(int(settings.PAYMENT_RECONCILIATION_MAX_AGE_SECONDS), minimum_age),
        30 * 24 * 60 * 60,
    )
    batch_size = min(max(int(settings.PAYMENT_RECONCILIATION_BATCH_SIZE), 1), 50)
    last_attempt_cutoff = current - timedelta(seconds=minimum_age)
    candidates = db.query(PaymentOrder.id).filter(
        PaymentOrder.provider == "qixiangpay",
        PaymentOrder.credited_at.is_(None),
        PaymentOrder.status.in_(("pending", "expired", "failed", "canceled")),
        PaymentOrder.created_at <= current - timedelta(seconds=minimum_age),
        PaymentOrder.created_at >= current - timedelta(seconds=maximum_age),
        or_(
            PaymentOrder.provider_trade_no.isnot(None),
            PaymentOrder.provider_checkout_url.isnot(None),
            PaymentOrder.checkout_started_at.isnot(None),
            PaymentOrder.provider_status.in_(("CREATE_PENDING", "CREATE_UNKNOWN", "0")),
        ),
        or_(
            PaymentOrder.last_reconciled_at.is_(None),
            PaymentOrder.last_reconciled_at <= last_attempt_cutoff,
        ),
    ).order_by(
        PaymentOrder.last_reconciled_at.asc(),
        PaymentOrder.id.asc(),
    ).limit(batch_size).all()

    for (payment_order_id,) in candidates:
        claimed = db.query(PaymentOrder).filter(
            PaymentOrder.id == payment_order_id,
            PaymentOrder.credited_at.is_(None),
            or_(
                PaymentOrder.last_reconciled_at.is_(None),
                PaymentOrder.last_reconciled_at <= last_attempt_cutoff,
            ),
        ).update(
            {
                PaymentOrder.last_reconciled_at: current,
                PaymentOrder.reconcile_attempts: PaymentOrder.reconcile_attempts + 1,
            },
            synchronize_session=False,
        )
        if claimed != 1:
            db.rollback()
            continue
        db.commit()
        counts["claimed"] += 1
        order = db.query(PaymentOrder).filter(
            PaymentOrder.id == payment_order_id
        ).first()
        if not order:
            continue
        try:
            query_provider_and_reconcile(db, order)
            counts["reconciled"] += 1
        except BizError as exc:
            db.rollback()
            current_order = db.query(PaymentOrder).filter(
                PaymentOrder.id == payment_order_id
            ).first()
            if current_order:
                record_payment_event(
                    db,
                    current_order.id,
                    "provider_reconciliation_error",
                    dedupe_key=(
                        f"payment:{current_order.id}:reconcile-error:"
                        f"{current_order.reconcile_attempts}"
                    ),
                    source="scheduler",
                    from_status=current_order.status,
                    to_status=current_order.status,
                    detail={"status_code": exc.status_code, "reason": exc.msg},
                )
                db.commit()
            counts["errors"] += 1
    return counts


def reconcile_payments_job() -> None:
    db = SessionLocal()
    try:
        stale_refunds = recover_stale_refund_submissions(db)
        db.commit()
        counts = reconcile_payment_orders(db)
        if stale_refunds or any(counts.values()):
            print(
                "[payment-reconciliation] "
                f"orders={counts}, stale_refunds={stale_refunds}"
            )
    except Exception as exc:  # noqa: BLE001
        db.rollback()
        # Service exceptions are intentionally string-only; provider request
        # objects (which can contain credentials) are never chained upstream.
        print(f"[payment-reconciliation] error: {type(exc).__name__}")
    finally:
        db.close()
