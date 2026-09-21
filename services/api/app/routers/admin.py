"""Administrator read APIs with auditable client-origin filtering.

``created_platform`` is an observability dimension copied from the server-side
authenticated session.  It is deliberately never used as an authorization
boundary: administrator access remains protected by ``require_admin``.
"""

from __future__ import annotations

import hashlib
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, Query
from sqlalchemy import and_, func, or_
from sqlalchemy.orm import Query as SqlAlchemyQuery, Session

from app.core.deps import require_admin
from app.core.rate_limit import limit_notification_broadcast, limit_payment_admin
from app.core.sensitive import reveal
from app.db.session import get_db
from app.models.bank_card import BankCard
from app.models.community import CommunityReport, Comment, Post
from app.models.external_identity import ExternalIdentity
from app.models.order import Order
from app.models.payment import PaymentEvent, PaymentOrder, PaymentRefund, PaymentRefundRequest
from app.models.product import Product
from app.models.user import User
from app.models.verification import Verification
from app.models.withdrawal import WithdrawalOrder
from app.schemas.community import CommunityReportReviewIn
from app.schemas.notification import NotificationBroadcastCreateIn
from app.schemas.payment import (
    PaymentRefundCreateIn,
    PaymentRefundRequestReviewIn,
    PaymentRefundResolveIn,
    PaymentReviewDecisionIn,
)
from app.services.auth_session import AUDIT_PLATFORMS, AuditPlatform
from app.services.product_provider import product_provider_info
from app.services.payment_operations import (
    event_out,
    refund_out,
    request_payment_refund,
    resolve_payment_review,
    resolve_unknown_refund,
)
from app.services.payment_refund_requests import (
    admin_refund_request_out,
    assert_no_active_customer_refund_request,
    get_admin_refund_request,
    list_admin_refund_requests,
    review_refund_request,
    sync_refund_request_for_payment_refund,
)
from app.services.notification_broadcast import create_broadcast, list_broadcasts
from app.utils.response import BizError, success


router = APIRouter(prefix="/api/admin", tags=["admin"])


def _utcnow() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)

def _page(page: int, page_size: int) -> None:
    if page < 1 or page_size < 1 or page_size > 100:
        raise BizError("分页参数无效")


def _filter_platform(
    query: SqlAlchemyQuery,
    model: type,
    platform: AuditPlatform | None,
) -> SqlAlchemyQuery:
    return query.filter(model.created_platform == platform) if platform else query


def _masked_phone(user: User) -> str | None:
    value = str(user.phone or "")
    if len(value) != 11 or not value.isdigit():
        return None
    return f"{value[:3]}****{value[-4:]}"


def _payment_order_out(db: Session, row: PaymentOrder) -> dict:
    owner = db.query(User).filter(User.id == row.user_id).first()
    return {
        "id": row.id,
        "order_no": row.order_no,
        "user": {"id": row.user_id, "username": owner.username if owner else None},
        "provider": row.provider,
        "provider_trade_no": row.provider_trade_no,
        "client_request_id": row.client_request_id,
        "channel": row.channel,
        "status": row.status,
        "provider_status": row.provider_status,
        "failure_reason": row.failure_reason,
        "amount_cny": float(row.amount_cny),
        "card_hours": float(row.card_hours),
        "card_hour_rate": float(row.card_hour_rate),
        "created_platform": row.created_platform or "legacy",
        "last_modified_platform": row.last_modified_platform or "legacy",
        "expires_at": row.expires_at,
        "paid_at": row.paid_at,
        "credited_at": row.credited_at,
        "last_reconciled_at": row.last_reconciled_at,
        "reconcile_attempts": row.reconcile_attempts,
        "created_at": row.created_at,
        "updated_at": row.updated_at,
    }


@router.get("/overview")
def overview(
    platform: AuditPlatform | None = None,
    actor: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    models = {
        "users": User,
        "orders": Order,
        "recharge_orders": PaymentOrder,
        "verifications": Verification,
        "bank_cards": BankCard,
        "withdrawals": WithdrawalOrder,
    }

    def counts_for(source: str | None) -> dict[str, int]:
        return {
            name: _filter_platform(db.query(model), model, source).count()
            for name, model in models.items()
        }

    sources = (platform,) if platform else AUDIT_PLATFORMS
    return success({
        "created_platform": platform,
        "counts": counts_for(platform),
        "by_platform": [
            {"created_platform": source, "counts": counts_for(source)}
            for source in sources
        ],
    })


@router.get("/notification-broadcasts")
def notification_broadcasts(
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    actor: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    """List durable administrator announcement audit records."""

    _page(page, page_size)
    return success(list_broadcasts(db, page=page, page_size=page_size))


@router.post("/notification-broadcasts")
def create_notification_broadcast(
    data: NotificationBroadcastCreateIn,
    actor: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    """Publish one announcement to every currently active account."""

    limit_notification_broadcast(actor.id)
    return success(create_broadcast(db, actor_user_id=actor.id, data=data))


@router.get("/users")
def users(
    platform: AuditPlatform | None = None,
    keyword: str | None = Query(default=None, max_length=64),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    actor: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    _page(page, page_size)
    query = _filter_platform(db.query(User), User, platform)
    if keyword:
        normalized = keyword.strip()
        if normalized:
            query = query.filter(
                (User.username.contains(normalized)) | (User.phone.contains(normalized))
            )
    total = query.count()
    rows = query.order_by(User.created_at.desc(), User.id.desc()).offset(
        (page - 1) * page_size
    ).limit(page_size).all()
    bound_user_ids = {
        row[0]
        for row in db.query(ExternalIdentity.user_id).filter(
            ExternalIdentity.provider == "kai",
            ExternalIdentity.user_id.in_([item.id for item in rows] or [-1]),
        ).all()
    }
    items = [{
        "id": row.id,
        "username": row.username,
        "phone_masked": _masked_phone(row),
        "phone_bound": bool(row.phone_bound),
        "role": row.role,
        "supplier_status": row.supplier_status,
        "kai_identity_bound": row.id in bound_user_ids,
        "created_platform": row.created_platform or "legacy",
        "created_at": row.created_at,
    } for row in rows]
    return success({"total": total, "page": page, "page_size": page_size, "items": items})


@router.get("/orders")
def orders(
    platform: AuditPlatform | None = None,
    status: str | None = Query(default=None, max_length=24),
    order_no: str | None = Query(default=None, max_length=40),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    actor: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    _page(page, page_size)
    query = _filter_platform(db.query(Order), Order, platform)
    if status:
        query = query.filter(Order.status == status)
    if order_no:
        query = query.filter(Order.order_no.contains(order_no.strip()))
    total = query.count()
    rows = query.order_by(Order.created_at.desc(), Order.id.desc()).offset(
        (page - 1) * page_size
    ).limit(page_size).all()
    items = []
    for row in rows:
        owner = db.query(User).filter(User.id == row.user_id).first()
        product = db.query(Product).filter(Product.id == row.product_id).first()
        provider = product_provider_info(product, db) if product else {
            "seller_type": None,
            "seller_name": None,
            "fulfillment_mode": None,
        }
        snapshot = dict(row.product_snapshot or {})
        plain_ssh = reveal(row.ssh_info) or ""
        ssh_info_present = bool(plain_ssh.strip())
        items.append({
            "id": row.id,
            "order_no": row.order_no,
            "user": {"id": row.user_id, "username": owner.username if owner else None},
            "product": {
                "id": row.product_id,
                "name": product.name if product else None,
                "gpu_model": product.gpu_model if product else None,
            },
            "quantity": row.quantity,
            "purchase_hours": row.purchase_hours,
            "cycle_days": row.cycle_days,
            "purchase_type": row.purchase_type,
            "amount_card_hours": float(row.amount),
            "status": row.status,
            "seller_type": snapshot.get("seller_type") or provider["seller_type"],
            "seller_name": snapshot.get("seller_name") or provider["seller_name"],
            "fulfillment_mode": provider["fulfillment_mode"],
            "product_snapshot": snapshot or None,
            "delivered_at": row.delivered_at,
            "confirmation_due_at": row.confirmation_due_at,
            "ssh_info_present": ssh_info_present,
            "ssh_info_fingerprint": (
                hashlib.sha256(plain_ssh.encode("utf-8")).hexdigest()[:16]
                if ssh_info_present else None
            ),
            "dispute_reason": row.dispute_reason,
            "disputed_at": row.disputed_at,
            "dispute_due_at": row.dispute_due_at,
            "dispute_resolution": row.dispute_resolution,
            "dispute_resolution_note": row.dispute_resolution_note,
            "dispute_resolved_at": row.dispute_resolved_at,
            "dispute_resolved_by": row.dispute_resolved_by,
            "created_platform": row.created_platform or "legacy",
            "last_modified_platform": row.last_modified_platform or "legacy",
            "start_at": row.start_at,
            "end_at": row.end_at,
            "created_at": row.created_at,
        })
    return success({"total": total, "page": page, "page_size": page_size, "items": items})


@router.get("/recharge-orders")
@router.get("/payment-orders", include_in_schema=False)
def recharge_orders(
    platform: AuditPlatform | None = None,
    status: str | None = Query(default=None, max_length=24),
    order_no: str | None = Query(default=None, max_length=40),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    actor: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    _page(page, page_size)
    query = _filter_platform(db.query(PaymentOrder), PaymentOrder, platform)
    if status:
        query = query.filter(PaymentOrder.status == status)
    if order_no:
        query = query.filter(PaymentOrder.order_no.contains(order_no.strip()))
    total = query.count()
    rows = query.order_by(PaymentOrder.created_at.desc(), PaymentOrder.id.desc()).offset(
        (page - 1) * page_size
    ).limit(page_size).all()
    items = [_payment_order_out(db, row) for row in rows]
    return success({"total": total, "page": page, "page_size": page_size, "items": items})


@router.get("/recharge-orders/{payment_order_id}")
def recharge_order_detail(
    payment_order_id: int,
    actor: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    limit_payment_admin(actor.id)
    row = db.query(PaymentOrder).filter(PaymentOrder.id == payment_order_id).first()
    if not row:
        raise BizError("充值订单不存在", status_code=404)
    events = db.query(PaymentEvent).filter(
        PaymentEvent.payment_order_id == row.id
    ).order_by(PaymentEvent.id.asc()).all()
    refund = db.query(PaymentRefund).filter(
        PaymentRefund.payment_order_id == row.id
    ).first()
    refund_request = db.query(PaymentRefundRequest).filter(
        PaymentRefundRequest.payment_order_id == row.id
    ).order_by(PaymentRefundRequest.id.desc()).first()
    return success({
        "order": _payment_order_out(db, row),
        "events": [event_out(item) for item in events],
        "refund": refund_out(refund) if refund else None,
        "refund_request": (
            admin_refund_request_out(db, refund_request) if refund_request else None
        ),
    })


@router.post("/recharge-orders/{payment_order_id}/review")
def review_recharge_order(
    payment_order_id: int,
    data: PaymentReviewDecisionIn,
    actor: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    limit_payment_admin(actor.id)
    if data.action == "refund":
        assert_no_active_customer_refund_request(db, payment_order_id)
    return success(resolve_payment_review(
        db,
        payment_order_id=payment_order_id,
        actor_user_id=actor.id,
        action=data.action,
        note=data.note,
        client_request_id=data.client_request_id,
    ))


@router.post("/recharge-orders/{payment_order_id}/refunds")
def create_payment_refund(
    payment_order_id: int,
    data: PaymentRefundCreateIn,
    actor: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    limit_payment_admin(actor.id)
    assert_no_active_customer_refund_request(db, payment_order_id)
    return success(request_payment_refund(
        db,
        payment_order_id=payment_order_id,
        actor_user_id=actor.id,
        client_request_id=data.client_request_id,
        reason=data.reason,
    ))


@router.get("/payment-refunds")
def payment_refunds(
    status: str | None = Query(default=None, max_length=24),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    actor: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    _page(page, page_size)
    query = db.query(PaymentRefund)
    if status:
        query = query.filter(PaymentRefund.status == status.strip())
    total = query.count()
    rows = query.order_by(PaymentRefund.created_at.desc(), PaymentRefund.id.desc()).offset(
        (page - 1) * page_size
    ).limit(page_size).all()
    return success({
        "total": total,
        "page": page,
        "page_size": page_size,
        "items": [refund_out(row) for row in rows],
    })


@router.get("/payment-refund-requests")
def payment_refund_requests(
    platform: AuditPlatform | None = None,
    status: str | None = Query(default=None, max_length=24),
    request_no: str | None = Query(default=None, max_length=40),
    order_no: str | None = Query(default=None, max_length=40),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    actor: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    _page(page, page_size)
    return success(list_admin_refund_requests(
        db,
        page=page,
        page_size=page_size,
        status=status,
        request_no=request_no,
        order_no=order_no,
        platform=platform,
    ))


@router.get("/payment-refund-requests/{request_id}")
def payment_refund_request_detail(
    request_id: int,
    actor: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    limit_payment_admin(actor.id)
    return success(get_admin_refund_request(db, request_id))


@router.post("/payment-refund-requests/{request_id}/review")
def review_payment_refund_request(
    request_id: int,
    data: PaymentRefundRequestReviewIn,
    actor: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    limit_payment_admin(actor.id)
    return success(review_refund_request(
        db,
        request_id=request_id,
        actor_user_id=actor.id,
        action=data.action,
        note=data.note,
    ))


@router.get("/payment-refunds/{refund_id}")
def payment_refund_detail(
    refund_id: int,
    actor: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    row = db.query(PaymentRefund).filter(PaymentRefund.id == refund_id).first()
    if not row:
        raise BizError("人民币退款记录不存在", status_code=404)
    return success(refund_out(row))


@router.post("/payment-refunds/{refund_id}/resolve")
def resolve_payment_refund(
    refund_id: int,
    data: PaymentRefundResolveIn,
    actor: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    limit_payment_admin(actor.id)
    result = resolve_unknown_refund(
        db,
        refund_id=refund_id,
        actor_user_id=actor.id,
        outcome=data.outcome,
        note=data.note,
    )
    sync_refund_request_for_payment_refund(db, refund_id)
    return success(result)


def _community_report_target(db: Session, report: CommunityReport) -> dict:
    if report.target_type == "post":
        target = db.get(Post, report.target_id)
        author = db.get(User, target.user_id) if target else None
        return {
            "exists": target is not None,
            "author": {"id": author.id, "username": author.username} if author else None,
            "excerpt": (target.content[:240] if target else None),
            "moderation_status": target.moderation_status if target else None,
        }
    if report.target_type == "comment":
        target = db.get(Comment, report.target_id)
        author = db.get(User, target.user_id) if target else None
        return {
            "exists": target is not None,
            "author": {"id": author.id, "username": author.username} if author else None,
            "excerpt": (target.content[:240] if target else None),
            "moderation_status": target.moderation_status if target else None,
        }
    target = db.get(User, report.target_id)
    return {
        "exists": target is not None,
        "author": {"id": target.id, "username": target.username} if target else None,
        "excerpt": None,
        "moderation_status": target.account_status if target else None,
    }


def _refresh_visible_comment_counts(db: Session, post_ids: set[int]) -> None:
    """Keep the legacy cached counter aligned with moderation visibility."""

    for post_id in post_ids:
        post = db.get(Post, post_id)
        if post is None:
            continue
        post.comments = int(db.query(func.count(Comment.id)).filter(
            Comment.post_id == post_id,
            Comment.moderation_status == "visible",
        ).scalar() or 0)


@router.get("/community/reports")
def community_reports(
    status: str | None = Query(default="pending", max_length=24),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    actor: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    _page(page, page_size)
    query = db.query(CommunityReport)
    if status:
        query = query.filter(CommunityReport.status == status)
    total = query.count()
    rows = query.order_by(
        CommunityReport.created_at.asc(), CommunityReport.id.asc()
    ).offset((page - 1) * page_size).limit(page_size).all()
    items = []
    for row in rows:
        reporter = db.get(User, row.reporter_user_id)
        items.append({
            "id": row.id,
            "target_type": row.target_type,
            "target_id": row.target_id,
            "reason": row.reason,
            "details": row.details,
            "status": row.status,
            "resolution": row.resolution,
            "resolution_note": row.resolution_note,
            "reporter": (
                {"id": reporter.id, "username": reporter.username}
                if reporter else None
            ),
            "target": _community_report_target(db, row),
            "created_platform": row.created_platform or "legacy",
            "created_at": row.created_at,
            "reviewed_at": row.reviewed_at,
        })
    return success({"total": total, "page": page, "page_size": page_size, "items": items})


@router.patch("/community/reports/{report_id}")
def review_community_report(
    report_id: int,
    data: CommunityReportReviewIn,
    actor: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    report = db.get(CommunityReport, report_id)
    if report is None:
        raise BizError("举报记录不存在", status_code=404)
    if report.status != "pending":
        raise BizError("举报已处理，请刷新审核队列", status_code=409)
    target, author = None, None
    affected_post_ids: set[int] = set()
    if report.target_type == "post":
        target = db.get(Post, report.target_id)
        author = db.get(User, target.user_id) if target else None
    elif report.target_type == "comment":
        target = db.get(Comment, report.target_id)
        author = db.get(User, target.user_id) if target else None
        if target is not None:
            affected_post_ids.add(int(target.post_id))
    else:
        author = db.get(User, report.target_id)

    if data.resolution == "content_removed" and target is None:
        raise BizError("被举报内容不存在", status_code=404)
    if data.resolution == "user_restricted" and author is None:
        raise BizError("被举报用户不存在", status_code=404)

    if data.resolution == "user_restricted":
        # Restricting an account is one moderation decision across that
        # account and all of its content. Claim every pending report in that
        # scope before mutating anything, so concurrent reviewers cannot
        # overwrite the first completed audit record through a sibling report.
        author_post_ids = db.query(Post.id).filter(Post.user_id == author.id)
        author_comment_ids = db.query(Comment.id).filter(Comment.user_id == author.id)
        review_scope = or_(
            and_(
                CommunityReport.target_type == "user",
                CommunityReport.target_id == author.id,
            ),
            and_(
                CommunityReport.target_type == "post",
                CommunityReport.target_id.in_(author_post_ids),
            ),
            and_(
                CommunityReport.target_type == "comment",
                CommunityReport.target_id.in_(author_comment_ids),
            ),
        )
    else:
        review_scope = and_(
            CommunityReport.target_type == report.target_type,
            CommunityReport.target_id == report.target_id,
        )

    claimed = db.query(CommunityReport).filter(
        review_scope,
        CommunityReport.status == "pending",
    ).update(
        {CommunityReport.status: "reviewing"},
        synchronize_session=False,
    )
    db.expire(report, ["status"])
    if claimed < 1 or report.status != "reviewing":
        db.rollback()
        raise BizError("举报已被其他管理员处理，请刷新审核队列", status_code=409)

    now = _utcnow()
    if data.resolution == "content_removed":
        target.moderation_status = "removed"
        target.moderation_reason = report.reason
        target.moderated_by = actor.id
        target.moderated_at = now
    elif data.resolution == "user_restricted":
        author.account_status = "suspended"
        db.query(Post).filter(
            Post.user_id == author.id,
            Post.moderation_status.in_(("visible", "pending_review")),
        ).update({
            Post.moderation_status: "removed",
            Post.moderation_reason: "account_restricted",
            Post.moderated_by: actor.id,
            Post.moderated_at: now,
        }, synchronize_session="fetch")
        affected_post_ids.update(
            int(row[0]) for row in db.query(Comment.post_id).filter(
                Comment.user_id == author.id,
                Comment.moderation_status.in_(("visible", "pending_review")),
            ).distinct().all()
        )
        db.query(Comment).filter(
            Comment.user_id == author.id,
            Comment.moderation_status.in_(("visible", "pending_review")),
        ).update({
            Comment.moderation_status: "removed",
            Comment.moderation_reason: "account_restricted",
            Comment.moderated_by: actor.id,
            Comment.moderated_at: now,
        }, synchronize_session="fetch")

    matching = db.query(CommunityReport).filter(
        review_scope,
        CommunityReport.status == "reviewing",
    ).all()
    for item in matching:
        item.status = "dismissed" if data.resolution == "dismissed" else "resolved"
        item.resolution = data.resolution
        item.resolution_note = data.note.strip() if data.note else None
        item.reviewed_by = actor.id
        item.reviewed_at = now

    if (
        data.resolution == "dismissed"
        and target is not None
        and target.moderation_status == "pending_review"
        and target.moderation_reason == "multiple_user_reports"
    ):
        target.moderation_status = "visible"
        target.moderation_reason = None
        target.moderated_by = actor.id
        target.moderated_at = now
    db.flush()
    _refresh_visible_comment_counts(db, affected_post_ids)
    db.commit()
    return success({
        "id": report.id,
        "status": report.status,
        "resolution": report.resolution,
    })
