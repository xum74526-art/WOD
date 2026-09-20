from __future__ import annotations

import re
import secrets
import threading
from datetime import datetime, timezone
from decimal import Decimal

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.models.payment import (
    PaymentOrder,
    PaymentRefund,
    PaymentRefundRequest,
)
from app.models.user import User
from app.services.auth_session import normalize_platform
from app.services.payment_operations import (
    REVIEW_STATUSES,
    record_payment_event,
    refund_out,
    request_payment_refund,
)
from app.utils.response import BizError


REFUND_REQUEST_STATUSES = frozenset({
    "pending_review",
    "approved",
    "processing",
    "rejected",
    "canceled",
    "succeeded",
    "failed",
})
ACTIVE_REFUND_REQUEST_STATUSES = frozenset({
    "pending_review",
    "approved",
    "processing",
})
_REFUND_REQUEST_LOCK = threading.Lock()


def _new_request_no() -> str:
    now = datetime.now(timezone.utc)
    return f"KAIRQA{now:%Y%m%d%H%M%S}{secrets.token_hex(4).upper()}"


def refund_request_out(
    row: PaymentRefundRequest,
    *,
    order_no: str,
) -> dict:
    return {
        "id": row.id,
        "request_no": row.request_no,
        "payment_order_id": row.payment_order_id,
        "order_no": order_no,
        "amount_cny": float(row.amount_cny),
        "card_hours": float(row.card_hours),
        "status": row.status,
        "reason": row.reason,
        "created_platform": row.created_platform,
        "reviewed_at": row.reviewed_at,
        "created_at": row.created_at,
        "updated_at": row.updated_at,
    }


def _validate_refundable_order(db: Session, order: PaymentOrder) -> None:
    if order.provider != "qixiangpay":
        raise BizError("历史充值订单暂不支持在线申请退款", status_code=409)
    if order.status == "refunded":
        raise BizError("该充值订单已经退款", status_code=409)
    if order.status in {"refund_pending", "refund_unknown"}:
        raise BizError("该充值订单已有退款流程正在处理", status_code=409)
    if order.status not in REVIEW_STATUSES and not (
        order.status == "paid" and order.credited_at is not None
    ):
        raise BizError("仅已确认支付或待复核的充值订单可申请退款", status_code=409)
    existing_refund = db.query(PaymentRefund).filter(
        PaymentRefund.payment_order_id == order.id
    ).first()
    if existing_refund:
        if existing_refund.status == "succeeded":
            raise BizError("该充值订单已经退款", status_code=409)
        raise BizError("该充值订单已有人民币退款流程，请联系平台核对", status_code=409)


def _idempotent_existing(
    db: Session,
    *,
    user_id: int,
    order: PaymentOrder,
    client_request_id: str,
    reason: str,
) -> dict | None:
    by_request = db.query(PaymentRefundRequest).filter(
        PaymentRefundRequest.user_id == user_id,
        PaymentRefundRequest.client_request_id == client_request_id,
    ).first()
    if by_request:
        if by_request.payment_order_id != order.id or by_request.reason != reason:
            raise BizError("退款申请幂等键已用于不同的订单或原因", status_code=409)
        return refund_request_out(by_request, order_no=order.order_no)

    active = db.query(PaymentRefundRequest).filter(
        PaymentRefundRequest.active_payment_order_id == order.id,
        PaymentRefundRequest.user_id == user_id,
        PaymentRefundRequest.status.in_(ACTIVE_REFUND_REQUEST_STATUSES),
    ).first()
    if active:
        return refund_request_out(active, order_no=order.order_no)
    return None


def create_refund_request(
    db: Session,
    *,
    user_id: int,
    order_no: str,
    client_request_id: str,
    reason: str,
    platform: str,
) -> dict:
    """Persist one review request without touching wallet/provider state."""
    normalized_request_id = str(client_request_id or "").strip()
    normalized_reason = " ".join(str(reason or "").split())
    if not re.fullmatch(r"[A-Za-z0-9._:-]{12,64}", normalized_request_id):
        raise BizError("退款申请幂等键格式无效", status_code=400)
    if len(normalized_reason) < 5 or len(normalized_reason) > 500:
        raise BizError("退款原因需为 5 至 500 个字符", status_code=400)

    # PostgreSQL serializes on the payment row; the process lock also closes
    # SQLite's SELECT FOR UPDATE gap in local/test environments.
    with _REFUND_REQUEST_LOCK:
        order = db.query(PaymentOrder).filter(
            PaymentOrder.order_no == str(order_no or "").strip(),
            PaymentOrder.user_id == user_id,
        ).populate_existing().with_for_update().first()
        if not order:
            raise BizError("充值订单不存在", status_code=404)

        existing = _idempotent_existing(
            db,
            user_id=user_id,
            order=order,
            client_request_id=normalized_request_id,
            reason=normalized_reason,
        )
        if existing:
            return existing
        _validate_refundable_order(db, order)

        row = PaymentRefundRequest(
            request_no=_new_request_no(),
            payment_order_id=order.id,
            active_payment_order_id=order.id,
            user_id=user_id,
            client_request_id=normalized_request_id,
            amount_cny=Decimal(order.amount_cny).quantize(Decimal("0.01")),
            card_hours=Decimal(order.card_hours).quantize(Decimal("0.000001")),
            status="pending_review",
            reason=normalized_reason,
            created_platform=normalize_platform(platform),
        )
        db.add(row)
        try:
            db.flush()
            record_payment_event(
                db,
                order.id,
                "customer_refund_requested",
                dedupe_key=f"payment:{order.id}:refund-request:{row.id}",
                actor_type="user",
                actor_user_id=user_id,
                source=row.created_platform,
                from_status=order.status,
                to_status=order.status,
                detail={
                    "request_no": row.request_no,
                    "amount_cny": f"{row.amount_cny:.2f}",
                },
            )
            db.commit()
        except IntegrityError as exc:
            db.rollback()
            order = db.query(PaymentOrder).filter(
                PaymentOrder.id == order.id,
                PaymentOrder.user_id == user_id,
            ).first()
            if order:
                existing = _idempotent_existing(
                    db,
                    user_id=user_id,
                    order=order,
                    client_request_id=normalized_request_id,
                    reason=normalized_reason,
                )
                if existing:
                    return existing
            raise BizError("退款申请幂等校验冲突，请稍后重试", status_code=409) from exc

        db.refresh(row)
        return refund_request_out(row, order_no=order.order_no)


def get_refund_request_for_order(
    db: Session,
    *,
    user_id: int,
    order_no: str,
) -> dict:
    result = db.query(PaymentRefundRequest, PaymentOrder.order_no).join(
        PaymentOrder,
        PaymentOrder.id == PaymentRefundRequest.payment_order_id,
    ).filter(
        PaymentOrder.order_no == str(order_no or "").strip(),
        PaymentOrder.user_id == user_id,
        PaymentRefundRequest.user_id == user_id,
    ).order_by(PaymentRefundRequest.id.desc()).first()
    if not result:
        # Do not reveal whether another user's payment exists.
        raise BizError("退款申请不存在", status_code=404)
    row, owned_order_no = result
    return refund_request_out(row, order_no=owned_order_no)


def list_owned_refund_requests(
    db: Session,
    *,
    user_id: int,
    page: int,
    page_size: int,
    status: str | None = None,
) -> dict:
    normalized_status = str(status or "").strip().lower()
    if normalized_status and normalized_status not in REFUND_REQUEST_STATUSES:
        raise BizError("退款申请状态无效", status_code=400)
    query = db.query(PaymentRefundRequest, PaymentOrder.order_no).join(
        PaymentOrder,
        PaymentOrder.id == PaymentRefundRequest.payment_order_id,
    ).filter(
        PaymentRefundRequest.user_id == user_id,
        PaymentOrder.user_id == user_id,
    )
    if normalized_status:
        query = query.filter(PaymentRefundRequest.status == normalized_status)
    total = query.count()
    rows = query.order_by(
        PaymentRefundRequest.created_at.desc(),
        PaymentRefundRequest.id.desc(),
    ).offset((page - 1) * page_size).limit(page_size).all()
    return {
        "items": [
            refund_request_out(row, order_no=owned_order_no)
            for row, owned_order_no in rows
        ],
        "page": page,
        "page_size": page_size,
        "total": total,
    }


def admin_refund_request_out(db: Session, row: PaymentRefundRequest) -> dict:
    order = db.query(PaymentOrder).filter(
        PaymentOrder.id == row.payment_order_id
    ).first()
    owner = db.query(User).filter(User.id == row.user_id).first()
    actual_refund = None
    if row.payment_refund_id:
        actual_refund = db.query(PaymentRefund).filter(
            PaymentRefund.id == row.payment_refund_id
        ).first()
    return {
        "id": row.id,
        "request_no": row.request_no,
        "payment_order_id": row.payment_order_id,
        "order_no": order.order_no if order else None,
        "payment_status": order.status if order else None,
        "user": {
            "id": row.user_id,
            "username": owner.username if owner else None,
        },
        "client_request_id": row.client_request_id,
        "amount_cny": float(row.amount_cny),
        "card_hours": float(row.card_hours),
        "status": row.status,
        "reason": row.reason,
        "created_platform": row.created_platform,
        "reviewed_by": row.reviewed_by,
        "review_note": row.review_note,
        "reviewed_at": row.reviewed_at,
        "payment_refund": refund_out(actual_refund) if actual_refund else None,
        "created_at": row.created_at,
        "updated_at": row.updated_at,
    }


def list_admin_refund_requests(
    db: Session,
    *,
    page: int,
    page_size: int,
    status: str | None = None,
    request_no: str | None = None,
    order_no: str | None = None,
    platform: str | None = None,
) -> dict:
    normalized_status = str(status or "").strip().lower()
    if normalized_status and normalized_status not in REFUND_REQUEST_STATUSES:
        raise BizError("退款申请状态无效", status_code=400)
    query = db.query(PaymentRefundRequest).join(
        PaymentOrder,
        PaymentOrder.id == PaymentRefundRequest.payment_order_id,
    )
    if normalized_status:
        query = query.filter(PaymentRefundRequest.status == normalized_status)
    if request_no:
        query = query.filter(
            PaymentRefundRequest.request_no.contains(request_no.strip().upper())
        )
    if order_no:
        query = query.filter(PaymentOrder.order_no.contains(order_no.strip().upper()))
    if platform:
        query = query.filter(PaymentRefundRequest.created_platform == platform)
    total = query.count()
    rows = query.order_by(
        PaymentRefundRequest.created_at.desc(),
        PaymentRefundRequest.id.desc(),
    ).offset((page - 1) * page_size).limit(page_size).all()
    return {
        "items": [admin_refund_request_out(db, row) for row in rows],
        "page": page,
        "page_size": page_size,
        "total": total,
    }


def get_admin_refund_request(db: Session, request_id: int) -> dict:
    row = db.query(PaymentRefundRequest).filter(
        PaymentRefundRequest.id == request_id
    ).first()
    if not row:
        raise BizError("充值退款申请不存在", status_code=404)
    return admin_refund_request_out(db, row)


def assert_no_active_customer_refund_request(
    db: Session,
    payment_order_id: int,
) -> None:
    pending = db.query(PaymentRefundRequest.id).filter(
        PaymentRefundRequest.active_payment_order_id == payment_order_id,
        PaymentRefundRequest.status.in_(ACTIVE_REFUND_REQUEST_STATUSES),
    ).first()
    if pending:
        raise BizError(
            "该充值订单已有用户退款申请，请在退款申请队列中审核",
            status_code=409,
        )


def _sync_request_from_refund(
    db: Session,
    request: PaymentRefundRequest,
    refund: PaymentRefund,
) -> None:
    previous = request.status
    request.payment_refund_id = refund.id
    if refund.status == "succeeded":
        request.status = "succeeded"
        request.active_payment_order_id = None
    elif refund.status == "failed":
        request.status = "failed"
        request.active_payment_order_id = None
    else:
        request.status = "processing"
        request.active_payment_order_id = request.payment_order_id
    record_payment_event(
        db,
        request.payment_order_id,
        "customer_refund_request_synced",
        dedupe_key=(
            f"payment:{request.payment_order_id}:refund-request:{request.id}:"
            f"refund:{refund.id}:{refund.status}"
        ),
        source="admin",
        from_status=None,
        to_status=None,
        detail={
            "request_no": request.request_no,
            "request_status_from": previous,
            "request_status_to": request.status,
            "refund_status": refund.status,
        },
    )


def sync_refund_request_for_payment_refund(
    db: Session,
    refund_id: int,
) -> dict | None:
    refund = db.query(PaymentRefund).filter(PaymentRefund.id == refund_id).first()
    if not refund:
        raise BizError("人民币退款记录不存在", status_code=404)
    request = db.query(PaymentRefundRequest).filter(
        (
            (PaymentRefundRequest.payment_refund_id == refund.id)
            | (
                (PaymentRefundRequest.payment_order_id == refund.payment_order_id)
                & (PaymentRefundRequest.status == "processing")
            )
        )
    ).order_by(PaymentRefundRequest.id.desc()).first()
    if not request:
        return None
    _sync_request_from_refund(db, request, refund)
    db.commit()
    db.refresh(request)
    return admin_refund_request_out(db, request)


def review_refund_request(
    db: Session,
    *,
    request_id: int,
    actor_user_id: int,
    action: str,
    note: str,
) -> dict:
    normalized_note = " ".join(str(note or "").split())
    if len(normalized_note) < 3 or len(normalized_note) > 500:
        raise BizError("审核说明需为 3 至 500 个字符", status_code=400)
    request = db.query(PaymentRefundRequest).filter(
        PaymentRefundRequest.id == request_id
    ).populate_existing().with_for_update().first()
    if not request:
        raise BizError("充值退款申请不存在", status_code=404)

    if action == "reject":
        if request.status == "rejected":
            return admin_refund_request_out(db, request)
        if request.status != "pending_review":
            raise BizError("当前退款申请状态不能驳回", status_code=409)
        existing_refund = db.query(PaymentRefund.id).filter(
            PaymentRefund.payment_order_id == request.payment_order_id
        ).first()
        if existing_refund:
            raise BizError("该申请已进入原路退款流程，不能驳回", status_code=409)
        request.status = "rejected"
        request.active_payment_order_id = None
        request.reviewed_by = actor_user_id
        request.review_note = normalized_note
        request.reviewed_at = datetime.now(timezone.utc).replace(tzinfo=None)
        order = db.query(PaymentOrder).filter(
            PaymentOrder.id == request.payment_order_id
        ).first()
        record_payment_event(
            db,
            request.payment_order_id,
            "customer_refund_request_rejected",
            dedupe_key=f"payment:{request.payment_order_id}:refund-request:{request.id}:rejected",
            actor_type="admin",
            actor_user_id=actor_user_id,
            source="admin",
            from_status=order.status if order else None,
            to_status=order.status if order else None,
            detail={"request_no": request.request_no},
        )
        db.commit()
        db.refresh(request)
        return admin_refund_request_out(db, request)

    if action != "approve":
        raise BizError("退款申请审核动作无效", status_code=400)
    if request.status in {"succeeded", "failed"}:
        return admin_refund_request_out(db, request)
    if request.status == "rejected":
        raise BizError("已驳回的退款申请不能直接批准", status_code=409)

    existing_refund = db.query(PaymentRefund).filter(
        PaymentRefund.payment_order_id == request.payment_order_id
    ).first()
    if request.status == "processing" or existing_refund:
        if not existing_refund:
            raise BizError("退款申请状态不完整，需人工核对", status_code=409)
        _sync_request_from_refund(db, request, existing_refund)
        db.commit()
        db.refresh(request)
        return admin_refund_request_out(db, request)
    if request.status != "pending_review":
        raise BizError("当前退款申请状态不能批准", status_code=409)

    request.status = "processing"
    request.reviewed_by = actor_user_id
    request.review_note = normalized_note
    request.reviewed_at = datetime.now(timezone.utc).replace(tzinfo=None)
    order = db.query(PaymentOrder).filter(
        PaymentOrder.id == request.payment_order_id
    ).first()
    record_payment_event(
        db,
        request.payment_order_id,
        "customer_refund_request_approved",
        dedupe_key=f"payment:{request.payment_order_id}:refund-request:{request.id}:approved",
        actor_type="admin",
        actor_user_id=actor_user_id,
        source="admin",
        from_status=order.status if order else None,
        to_status=order.status if order else None,
        detail={"request_no": request.request_no},
    )
    stable_refund_id = f"refund-application-{request.id}-{request.request_no}"
    try:
        refund_result = request_payment_refund(
            db,
            payment_order_id=request.payment_order_id,
            actor_user_id=actor_user_id,
            client_request_id=stable_refund_id,
            reason=(
                f"用户申请：{request.reason}；管理员审核：{normalized_note}"
            )[:500],
            customer_refund_request_id=request.id,
        )
    except BizError:
        db.rollback()
        actual_refund = db.query(PaymentRefund).filter(
            PaymentRefund.payment_order_id == request.payment_order_id
        ).first()
        if actual_refund:
            current = db.query(PaymentRefundRequest).filter(
                PaymentRefundRequest.id == request_id
            ).first()
            if current and current.status == "processing":
                _sync_request_from_refund(db, current, actual_refund)
                db.commit()
        raise

    actual_refund = db.query(PaymentRefund).filter(
        PaymentRefund.id == refund_result["id"]
    ).first()
    current = db.query(PaymentRefundRequest).filter(
        PaymentRefundRequest.id == request_id
    ).first()
    if not actual_refund or not current:
        raise BizError("退款审核结果写入不完整，需人工核对", status_code=409)
    _sync_request_from_refund(db, current, actual_refund)
    db.commit()
    db.refresh(current)
    return admin_refund_request_out(db, current)
