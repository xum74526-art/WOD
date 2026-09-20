from __future__ import annotations

import secrets
import threading
from datetime import datetime, timedelta, timezone
from decimal import Decimal

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.config import settings
from app.models.ledger import Ledger
from app.models.payment import PaymentEvent, PaymentOrder, PaymentRefund
from app.models.wallet import Wallet
from app.services.wallet_balance import spendable_wallet_balance
from app.utils.response import BizError


REVIEW_STATUSES = frozenset({"review", "late_paid_review"})
REFUND_ACTIVE_STATUSES = frozenset({"preparing", "submitting", "unknown"})
_PAYMENT_REFUND_LOCK = threading.Lock()
_FORBIDDEN_DETAIL_FRAGMENTS = (
    "secret", "password", "private_key", "merchant_key", "signature", "token",
)
_FORBIDDEN_DETAIL_KEYS = frozenset({
    "key",
    "sign",
    "card",
    "card_no",
    "card_number",
    "bank_card",
    "bank_account",
    "account",
    "account_no",
    "account_number",
})


def utc_now() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


def _safe_detail(detail: dict | None) -> dict | None:
    if not detail:
        return None
    output: dict[str, str | int | float | bool | None] = {}
    for raw_key, raw_value in detail.items():
        key = str(raw_key)[:48]
        lowered = key.lower()
        if lowered in _FORBIDDEN_DETAIL_KEYS or any(
            fragment in lowered for fragment in _FORBIDDEN_DETAIL_FRAGMENTS
        ):
            raise ValueError("sensitive payment event detail key")
        if raw_value is None or isinstance(raw_value, (bool, int, float)):
            output[key] = raw_value
        else:
            output[key] = str(raw_value)[:160]
    return output or None


def record_payment_event(
    db: Session,
    payment_order_id: int,
    event_type: str,
    *,
    dedupe_key: str,
    actor_type: str = "system",
    actor_user_id: int | None = None,
    source: str = "system",
    from_status: str | None = None,
    to_status: str | None = None,
    detail: dict | None = None,
) -> PaymentEvent:
    existing = db.query(PaymentEvent).filter(
        PaymentEvent.dedupe_key == dedupe_key[:160]
    ).first()
    if existing:
        return existing
    row = PaymentEvent(
        payment_order_id=payment_order_id,
        event_type=event_type[:48],
        actor_type=actor_type[:16],
        actor_user_id=actor_user_id,
        source=source[:32],
        from_status=from_status[:24] if from_status else None,
        to_status=to_status[:24] if to_status else None,
        dedupe_key=dedupe_key[:160],
        detail=_safe_detail(detail),
    )
    db.add(row)
    return row


def event_out(row: PaymentEvent) -> dict:
    return {
        "id": row.id,
        "payment_order_id": row.payment_order_id,
        "event_type": row.event_type,
        "actor_type": row.actor_type,
        "actor_user_id": row.actor_user_id,
        "source": row.source,
        "from_status": row.from_status,
        "to_status": row.to_status,
        "detail": row.detail,
        "created_at": row.created_at,
    }


def refund_out(row: PaymentRefund) -> dict:
    return {
        "id": row.id,
        "refund_no": row.refund_no,
        "payment_order_id": row.payment_order_id,
        "actor_user_id": row.actor_user_id,
        "client_request_id": row.client_request_id,
        "amount_cny": float(row.amount_cny),
        "card_hours": float(row.card_hours),
        "status": row.status,
        "wallet_hold_status": row.wallet_hold_status,
        "previous_payment_status": row.previous_payment_status,
        "reason": row.reason,
        "provider_code": row.provider_code,
        "provider_message": row.provider_message,
        "resolution_note": row.resolution_note,
        "attempt_count": row.attempt_count,
        "requested_at": row.requested_at,
        "resolved_at": row.resolved_at,
        "created_at": row.created_at,
        "updated_at": row.updated_at,
    }


def _refundable_recharge_balance(wallet: Wallet, db: Session) -> Decimal:
    """Conservatively isolate available non-promotional, non-earnings funds."""
    spendable = Decimal(str(spendable_wallet_balance(wallet, db)))
    promotional = Decimal(str(wallet.promotional_balance or 0))
    return max(Decimal("0.000000"), spendable - promotional).quantize(
        Decimal("0.000001")
    )


def _freeze_refund_card_hours(
    db: Session,
    order: PaymentOrder,
    refund: PaymentRefund,
) -> None:
    if order.credited_at is None:
        refund.wallet_hold_status = "not_required"
        return
    amount = Decimal(order.card_hours).quantize(Decimal("0.000001"))
    wallet = db.query(Wallet).filter(
        Wallet.user_id == order.user_id
    ).with_for_update().first()
    if not wallet:
        raise BizError("钱包不存在", status_code=404)
    if _refundable_recharge_balance(wallet, db) < amount:
        raise BizError(
            "无法可靠保留等额可退充值卡时，需转人工核对后处理",
            status_code=409,
        )
    wallet.balance = (Decimal(wallet.balance) - amount).quantize(Decimal("0.000001"))
    wallet.frozen = (Decimal(wallet.frozen) + amount).quantize(Decimal("0.000001"))
    refund.wallet_hold_status = "held"


def _release_refund_hold(
    db: Session,
    order: PaymentOrder,
    refund: PaymentRefund,
) -> None:
    if refund.wallet_hold_status != "held":
        return
    amount = Decimal(refund.card_hours).quantize(Decimal("0.000001"))
    wallet = db.query(Wallet).filter(
        Wallet.user_id == order.user_id
    ).with_for_update().first()
    if not wallet or Decimal(wallet.frozen) < amount:
        raise BizError("退款冻结资金不一致，必须人工核对", status_code=409)
    wallet.frozen = (Decimal(wallet.frozen) - amount).quantize(Decimal("0.000001"))
    wallet.balance = (Decimal(wallet.balance) + amount).quantize(Decimal("0.000001"))
    refund.wallet_hold_status = "released"


def _settle_refund_hold(
    db: Session,
    order: PaymentOrder,
    refund: PaymentRefund,
) -> None:
    if refund.wallet_hold_status == "settled":
        return
    if refund.wallet_hold_status == "not_required":
        return
    if refund.wallet_hold_status != "held":
        raise BizError("退款冻结状态不一致，必须人工核对", status_code=409)
    amount = Decimal(refund.card_hours).quantize(Decimal("0.000001"))
    wallet = db.query(Wallet).filter(
        Wallet.user_id == order.user_id
    ).with_for_update().first()
    if not wallet or Decimal(wallet.frozen) < amount:
        raise BizError("退款冻结资金不足，必须人工核对", status_code=409)
    wallet.frozen = (Decimal(wallet.frozen) - amount).quantize(Decimal("0.000001"))
    refund.wallet_hold_status = "settled"
    db.add(Ledger(
        user_id=order.user_id,
        wallet_id=wallet.id,
        type="payment_refund",
        direction="out",
        amount=amount,
        balance_after=Decimal(wallet.balance).quantize(Decimal("0.000001")),
        ref_payment_refund_id=refund.id,
        event_key=f"payment-refund:{refund.id}:settled",
        remark=(
            f"七相支付人民币 {Decimal(refund.amount_cny):.2f} 元原路退款，"
            f"扣减 {amount} 卡时"
        ),
    ))


def _load_refund_context(
    db: Session,
    refund_id: int,
) -> tuple[PaymentRefund, PaymentOrder]:
    refund = db.query(PaymentRefund).filter(
        PaymentRefund.id == refund_id
    ).with_for_update().first()
    if not refund:
        raise BizError("人民币退款记录不存在", status_code=404)
    order = db.query(PaymentOrder).filter(
        PaymentOrder.id == refund.payment_order_id
    ).with_for_update().first()
    if not order:
        raise BizError("充值订单不存在", status_code=404)
    return refund, order


def _mark_refund_succeeded(
    db: Session,
    refund: PaymentRefund,
    order: PaymentOrder,
    *,
    actor_user_id: int | None = None,
    source: str,
    note: str | None = None,
) -> None:
    previous = order.status
    _settle_refund_hold(db, order, refund)
    refund.status = "succeeded"
    refund.resolved_at = utc_now()
    if note:
        refund.resolution_note = note[:500]
    order.status = "refunded"
    order.failure_reason = None
    order.last_modified_platform = "admin" if actor_user_id else "system"
    record_payment_event(
        db,
        order.id,
        "provider_refund_succeeded",
        dedupe_key=f"payment:{order.id}:refund:{refund.id}:succeeded",
        actor_type="admin" if actor_user_id else "system",
        actor_user_id=actor_user_id,
        source=source,
        from_status=previous,
        to_status="refunded",
        detail={"refund_no": refund.refund_no, "amount_cny": f"{refund.amount_cny:.2f}"},
    )


def _mark_refund_failed(
    db: Session,
    refund: PaymentRefund,
    order: PaymentOrder,
    *,
    actor_user_id: int | None = None,
    source: str,
    note: str | None = None,
) -> None:
    previous = order.status
    _release_refund_hold(db, order, refund)
    refund.status = "failed"
    refund.resolved_at = utc_now()
    if note:
        refund.resolution_note = note[:500]
    order.status = refund.previous_payment_status
    order.last_modified_platform = "admin" if actor_user_id else "system"
    record_payment_event(
        db,
        order.id,
        "provider_refund_failed",
        dedupe_key=(
            f"payment:{order.id}:refund:{refund.id}:failed:{refund.attempt_count}"
        ),
        actor_type="admin" if actor_user_id else "system",
        actor_user_id=actor_user_id,
        source=source,
        from_status=previous,
        to_status=order.status,
        detail={"refund_no": refund.refund_no, "provider_code": refund.provider_code},
    )


def request_payment_refund(
    db: Session,
    *,
    payment_order_id: int,
    actor_user_id: int,
    client_request_id: str,
    reason: str,
) -> dict:
    # SQLite ignores SELECT FOR UPDATE in local/test deployments. PostgreSQL's
    # row lock and unique refund/order constraint protect production workers;
    # this lock closes the same-process SQLite gap and keeps tests realistic.
    with _PAYMENT_REFUND_LOCK:
        return _request_payment_refund_locked(
            db,
            payment_order_id=payment_order_id,
            actor_user_id=actor_user_id,
            client_request_id=client_request_id,
            reason=reason,
        )


def _request_payment_refund_locked(
    db: Session,
    *,
    payment_order_id: int,
    actor_user_id: int,
    client_request_id: str,
    reason: str,
) -> dict:
    """Submit one full Qixiang original-rail refund with a durable wallet hold."""
    order = db.query(PaymentOrder).filter(
        PaymentOrder.id == payment_order_id
    ).populate_existing().with_for_update().first()
    if not order:
        raise BizError("充值订单不存在", status_code=404)
    if order.provider != "qixiangpay":
        raise BizError("历史 MaPay 订单不支持通过七相接口退款", status_code=409)

    normalized_request_id = str(client_request_id or "").strip()
    existing = db.query(PaymentRefund).filter(
        PaymentRefund.payment_order_id == order.id
    ).first()
    if existing:
        if (
            existing.actor_user_id != actor_user_id
            or existing.client_request_id != normalized_request_id
        ):
            raise BizError("该充值订单已有人民币退款流程", status_code=409)
        if existing.status in REFUND_ACTIVE_STATUSES or existing.status == "succeeded":
            return refund_out(existing)
        if existing.status != "failed":
            raise BizError("人民币退款状态不允许重试", status_code=409)
        refund = existing
        refund.status = "preparing"
        refund.resolved_at = None
        refund.provider_code = None
        refund.provider_message = None
        refund.resolution_note = None
        refund.reason = reason[:500]
    else:
        refund = None

    if order.status not in REVIEW_STATUSES and order.credited_at is None:
        raise BizError("仅已确认支付或待复核的充值订单可发起退款", status_code=409)

    from app.services.qixiangpay import assert_provider_refund_ready

    # Fail before touching wallet state when the request is certainly unable
    # to leave this process (disabled capability, missing merchant settings,
    # invalid order identity).
    assert_provider_refund_ready(order)

    if refund is None:
        refund = PaymentRefund(
            refund_no=(
                f"KAIR{datetime.now():%Y%m%d%H%M%S}{secrets.token_hex(4).upper()}"
            ),
            payment_order_id=order.id,
            actor_user_id=actor_user_id,
            client_request_id=normalized_request_id,
            amount_cny=Decimal(order.amount_cny).quantize(Decimal("0.01")),
            card_hours=Decimal(order.card_hours).quantize(Decimal("0.000001")),
            status="preparing",
            wallet_hold_status="not_required",
            previous_payment_status=order.status,
            reason=reason[:500],
        )
        db.add(refund)
        try:
            db.flush()
        except IntegrityError as exc:
            db.rollback()
            raise BizError("人民币退款幂等校验冲突", status_code=409) from exc

    # Claim the payment state with a compare-and-swap before freezing funds.
    # PostgreSQL's row lock already serializes this with callback crediting, but
    # SQLite ignores SELECT FOR UPDATE.  The predicate makes either the credit
    # or the refund claim win; a stale review object can never be refunded as
    # "not_required" after a callback has just credited its wallet.
    previous = order.status
    # A failed refund can legitimately be retried after an intervening review
    # credit.  Restore to the state at *this* attempt, never the first attempt's
    # stale state, if the provider rejects the retry definitively.
    refund.previous_payment_status = previous
    credit_filter = (
        PaymentOrder.credited_at.is_(None)
        if order.credited_at is None
        else PaymentOrder.credited_at == order.credited_at
    )
    claimed = db.query(PaymentOrder).filter(
        PaymentOrder.id == order.id,
        PaymentOrder.status == previous,
        credit_filter,
    ).update(
        {
            PaymentOrder.status: "refund_pending",
            PaymentOrder.last_modified_platform: "admin",
        },
        synchronize_session=False,
    )
    if claimed != 1:
        db.rollback()
        raise BizError("充值订单状态已变化，请刷新后重试退款", status_code=409)

    order.status = "refund_pending"
    order.last_modified_platform = "admin"
    _freeze_refund_card_hours(db, order, refund)
    refund.status = "submitting"
    refund.attempt_count = int(refund.attempt_count or 0) + 1
    submission_attempt = refund.attempt_count
    refund.requested_at = utc_now()
    record_payment_event(
        db,
        order.id,
        "provider_refund_submitting",
        dedupe_key=(
            f"payment:{order.id}:refund:{refund.id}:submit:{refund.attempt_count}"
        ),
        actor_type="admin",
        actor_user_id=actor_user_id,
        source="admin",
        from_status=previous,
        to_status="refund_pending",
        detail={"refund_no": refund.refund_no, "amount_cny": f"{refund.amount_cny:.2f}"},
    )
    db.commit()

    from app.services.qixiangpay import ProviderRefundUncertain, submit_provider_refund

    try:
        provider_result = submit_provider_refund(order)
    except ProviderRefundUncertain:
        db.rollback()
        refund, order = _load_refund_context(db, refund.id)
        if refund.status == "submitting":
            refund.status = "unknown"
            order.status = "refund_unknown"
            record_payment_event(
                db,
                order.id,
                "provider_refund_unknown",
                dedupe_key=(
                    f"payment:{order.id}:refund:{refund.id}:unknown:{refund.attempt_count}"
                ),
                actor_type="system",
                source="provider",
                from_status="refund_pending",
                to_status="refund_unknown",
                detail={"refund_no": refund.refund_no},
            )
            db.commit()
        return refund_out(refund)
    except BizError as exc:
        # A local precondition failed before a request could be sent.  Restore
        # the hold and surface the failure; do not strand funds as unknown.
        db.rollback()
        refund, order = _load_refund_context(db, refund.id)
        refund.provider_message = exc.msg[:160]
        _mark_refund_failed(db, refund, order, source="local_preflight")
        db.commit()
        raise

    db.rollback()
    provider_code = str(provider_result.get("code") or "")[:32] or None
    provider_message = str(provider_result.get("msg") or "")[:160] or None
    finalizing = db.query(PaymentRefund).filter(
        PaymentRefund.id == refund.id,
        PaymentRefund.status == "submitting",
        PaymentRefund.attempt_count == submission_attempt,
    ).update(
        {
            PaymentRefund.status: "finalizing",
            PaymentRefund.provider_code: provider_code,
            PaymentRefund.provider_message: provider_message,
        },
        synchronize_session=False,
    )
    if finalizing != 1:
        db.rollback()
        refund, order = _load_refund_context(db, refund.id)
        record_payment_event(
            db,
            order.id,
            "provider_refund_late_result",
            dedupe_key=(
                f"payment:{order.id}:refund:{refund.id}:late-result:"
                f"{submission_attempt}:{'success' if provider_result.get('success') else 'failed'}"
            ),
            source="provider",
            from_status=order.status,
            to_status=order.status,
            detail={
                "refund_no": refund.refund_no,
                "provider_code": provider_code,
                "provider_success": bool(provider_result.get("success")),
            },
        )
        db.commit()
        return refund_out(refund)

    refund, order = _load_refund_context(db, refund.id)
    if provider_result.get("success"):
        _mark_refund_succeeded(db, refund, order, source="provider")
    else:
        _mark_refund_failed(db, refund, order, source="provider")
    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise BizError("人民币退款入账幂等校验失败，必须人工核对", status_code=409) from exc
    db.refresh(refund)
    return refund_out(refund)


def resolve_unknown_refund(
    db: Session,
    *,
    refund_id: int,
    actor_user_id: int,
    outcome: str,
    note: str,
) -> dict:
    refund, order = _load_refund_context(db, refund_id)
    if refund.status == "succeeded" and outcome == "succeeded":
        return refund_out(refund)
    if refund.status == "failed" and outcome == "failed":
        return refund_out(refund)
    if refund.status != "unknown":
        raise BizError("仅结果不确定的人民币退款可人工确认", status_code=409)
    if refund.actor_user_id == actor_user_id:
        raise BizError(
            "退款结果必须由另一名管理员依据商户后台证据复核",
            status_code=409,
        )
    if outcome == "succeeded":
        _mark_refund_succeeded(
            db,
            refund,
            order,
            actor_user_id=actor_user_id,
            source="admin_provider_evidence",
            note=note,
        )
    elif outcome == "failed":
        _mark_refund_failed(
            db,
            refund,
            order,
            actor_user_id=actor_user_id,
            source="admin_provider_evidence",
            note=note,
        )
    else:
        raise BizError("退款确认结果无效", status_code=400)
    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise BizError("人民币退款确认冲突，必须人工核对", status_code=409) from exc
    db.refresh(refund)
    return refund_out(refund)


def recover_stale_refund_submissions(db: Session, *, now: datetime | None = None) -> int:
    current = now or utc_now()
    timeout = min(
        max(int(settings.PAYMENT_REFUND_SUBMISSION_TIMEOUT_SECONDS), 60),
        3600,
    )
    stale_ids = db.query(PaymentRefund.id).filter(
        PaymentRefund.status == "submitting",
        PaymentRefund.requested_at <= current - timedelta(seconds=timeout),
    ).order_by(PaymentRefund.id.asc()).limit(50).all()
    changed = 0
    cutoff = current - timedelta(seconds=timeout)
    for (refund_id,) in stale_ids:
        # Compare-and-swap the refund first, matching the lock order used by
        # manual resolution (refund -> payment order).  A finance operator may
        # resolve a stale ``submitting`` row after candidate selection; in that
        # case this update affects zero rows and recovery must not overwrite the
        # terminal result or its wallet/ledger settlement.
        claimed = db.query(PaymentRefund).filter(
            PaymentRefund.id == refund_id,
            PaymentRefund.status == "submitting",
            PaymentRefund.requested_at <= cutoff,
        ).update(
            {PaymentRefund.status: "unknown"},
            synchronize_session=False,
        )
        if claimed != 1:
            db.rollback()
            continue
        refund = db.query(PaymentRefund).filter(
            PaymentRefund.id == refund_id
        ).populate_existing().first()
        if not refund:
            db.rollback()
            continue
        order_claimed = db.query(PaymentOrder).filter(
            PaymentOrder.id == refund.payment_order_id,
            PaymentOrder.status == "refund_pending",
        ).update(
            {PaymentOrder.status: "refund_unknown"},
            synchronize_session=False,
        )
        if order_claimed != 1:
            db.rollback()
            continue
        record_payment_event(
            db,
            refund.payment_order_id,
            "provider_refund_unknown",
            dedupe_key=(
                f"payment:{refund.payment_order_id}:refund:{refund.id}:"
                f"stale:{refund.attempt_count}"
            ),
            source="recovery",
            from_status="refund_pending",
            to_status="refund_unknown",
            detail={"refund_no": refund.refund_no},
        )
        db.commit()
        changed += 1
    return changed


def resolve_payment_review(
    db: Session,
    *,
    payment_order_id: int,
    actor_user_id: int,
    action: str,
    note: str,
    client_request_id: str | None = None,
) -> dict:
    order = db.query(PaymentOrder).filter(
        PaymentOrder.id == payment_order_id
    ).with_for_update().first()
    if not order:
        raise BizError("充值订单不存在", status_code=404)
    if order.status not in REVIEW_STATUSES:
        if action == "credit" and order.credited_at is not None:
            return {"order_id": order.id, "status": order.status, "credited": True}
        raise BizError("充值订单不在待复核状态", status_code=409)
    if action == "refund":
        if not client_request_id:
            raise BizError("发起人民币退款必须提供幂等键", status_code=400)
        db.rollback()
        return request_payment_refund(
            db,
            payment_order_id=payment_order_id,
            actor_user_id=actor_user_id,
            client_request_id=client_request_id,
            reason=note,
        )
    if action != "credit":
        raise BizError("支付复核动作无效", status_code=400)

    if order.provider == "qixiangpay":
        from app.services import qixiangpay

        payload = qixiangpay._query_provider_payload(db, order)
        if not qixiangpay._provider_reports_success(payload):
            raise BizError("七相支付尚未确认成功，不能人工入账", status_code=409)
        normalized = dict(payload)
        normalized["trade_status"] = qixiangpay.SUCCESS_STATUS
        credited = qixiangpay.credit_verified_payment(
            db,
            order,
            normalized,
            observed_at=utc_now(),
            review_override=True,
            actor_user_id=actor_user_id,
            review_note=note,
        )
    elif order.provider == "mapay":
        from app.services import mapay

        payload = mapay._query_provider_payload(order)
        if not mapay._provider_reports_success(payload):
            raise BizError("MaPay 尚未确认成功，不能人工入账", status_code=409)
        normalized = dict(payload)
        normalized["trade_status"] = mapay.SUCCESS_STATUS
        credited = mapay.credit_verified_payment(
            db,
            order,
            normalized,
            observed_at=utc_now(),
            review_override=True,
            actor_user_id=actor_user_id,
            review_note=note,
        )
    else:
        raise BizError("充值订单支付渠道无效", status_code=409)
    current = db.query(PaymentOrder).filter(PaymentOrder.id == order.id).first()
    return {
        "order_id": order.id,
        "status": current.status if current else order.status,
        "credited": bool(credited or (current and current.credited_at)),
    }
