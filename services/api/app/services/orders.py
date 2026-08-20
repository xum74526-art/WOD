from datetime import datetime, timezone
import re

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, aliased

from app.domain.commerce import BUY_REQUEST_TRANSITIONS, ORDER_TRANSITIONS, can_transition
from app.models import (
    BuyRequest,
    BuyRequestEvent,
    Order,
    OrderEvent,
    SupplierApplication,
    User,
)
from app.security import ApiError
from app.services.quotes import order_out as quote_order_out
from app.services import resources as resource_service
from app.services.internal_modules import create_notification


ORDER_STATUSES = (
    "pending_confirmation",
    "confirmed",
    "delivering",
    "delivered",
    "completed",
    "cancelled",
)
CANCELLABLE_STATUSES = ("pending_confirmation", "confirmed")
SENSITIVE_DELIVERY_PATTERNS = (
    re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----", re.IGNORECASE),
    re.compile(r"\bssh-(?:rsa|ed25519)\s+[A-Za-z0-9+/=]+", re.IGNORECASE),
    re.compile(r"\b(?:password|passwd|token|secret)\s*[:=]", re.IGNORECASE),
    re.compile(r"密码\s*[:：=]"),
)


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _check_version(order: Order, version: int) -> None:
    if order.version != version:
        raise ApiError("ORDER_VERSION_CONFLICT", "订单已被更新，请刷新后重试", 409)


def _validate_delivery_note(note: str | None) -> None:
    if note and any(pattern.search(note) for pattern in SENSITIVE_DELIVERY_PATTERNS):
        raise ApiError(
            "DELIVERY_CREDENTIALS_FORBIDDEN",
            "交付说明不能包含密码、私钥、Token 或其他登录凭据",
            422,
        )


def _require_supplier(user: User) -> None:
    if user.role != "supplier":
        raise ApiError("SUPPLIER_REQUIRED", "仅商家可以访问商家订单", 403)


def _owned_order(
    db: Session,
    user: User,
    order_id: int,
    *,
    scope: str,
    lock: bool = False,
) -> Order:
    if scope == "supplier":
        _require_supplier(user)
        ownership = Order.supplier_id == user.id
    else:
        ownership = Order.buyer_id == user.id
    query = db.query(Order).filter(Order.id == order_id, ownership)
    if lock:
        query = query.with_for_update()
    order = query.first()
    if order is None:
        raise ApiError("ORDER_NOT_FOUND", "订单不存在", 404)
    return order


def _event(
    db: Session,
    order: Order,
    user: User,
    *,
    event_type: str,
    from_status: str,
    to_status: str,
    note: str | None = None,
    extra: dict | None = None,
) -> None:
    payload = dict(extra or {})
    if note:
        payload["note"] = note
    db.add(OrderEvent(
        order_id=order.id,
        actor_user_id=user.id,
        actor_role=user.role,
        event_type=event_type,
        from_status=from_status,
        to_status=to_status,
        payload=payload,
    ))


def _notify_counterparty(db: Session, order: Order, actor: User, title: str, body: str) -> None:
    target_id = order.supplier_id if actor.id == order.buyer_id else order.buyer_id
    action_path = "/supplier/orders" if target_id == order.supplier_id else "/account/orders"
    create_notification(
        db,
        user_id=target_id,
        category="order",
        title=title,
        body=body,
        action_path=action_path,
    )


def _commit(db: Session) -> None:
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise ApiError("ORDER_CONFLICT", "订单状态更新冲突，请刷新后重试", 409)


def _actions(order: Order, scope: str) -> list[str]:
    if scope == "buyer":
        actions = []
        if order.status in CANCELLABLE_STATUSES:
            actions.append("cancel")
        if order.status == "delivered" and order.order_source != "direct":
            actions.append("complete")
        return actions
    if order.order_source == "direct":
        return []
    actions = []
    if (
        order.status == "pending_confirmation"
        and order.supplier_confirmed_at is None
        and order.payment_status in ("not_required", "paid")
    ):
        actions.append("confirm")
    if order.status in CANCELLABLE_STATUSES:
        actions.append("cancel")
    if order.status == "confirmed":
        actions.append("start_delivery")
    if order.status == "delivering":
        actions.append("mark_delivered")
    return actions


def order_out(
    order: Order,
    *,
    scope: str,
    buyer: User,
    supplier: User,
    application: SupplierApplication | None,
    events: list[OrderEvent] | None = None,
) -> dict:
    data = order_summary_out(order)
    data["buyer"] = {"display_name": buyer.display_name}
    data["supplier"] = {
        "display_name": supplier.display_name,
        "company_name": application.company_name if application else None,
    }
    data["available_actions"] = _actions(order, scope)
    if events is not None:
        data["events"] = [
            {
                "id": event.id,
                "actor_role": event.actor_role,
                "event_type": event.event_type,
                "from_status": event.from_status,
                "to_status": event.to_status,
                "payload": event.payload or {},
                "created_at": event.created_at,
            }
            for event in events
        ]
    return data


def order_summary_out(order: Order) -> dict:
    return quote_order_out(order)


def list_orders(
    db: Session,
    user: User,
    *,
    scope: str,
    page: int,
    page_size: int,
    status: str | None,
) -> tuple[list[tuple[Order, User, User, SupplierApplication | None]], int]:
    if scope == "supplier":
        _require_supplier(user)
        ownership = Order.supplier_id == user.id
    else:
        ownership = Order.buyer_id == user.id
    Buyer = aliased(User)
    Supplier = aliased(User)
    query = (
        db.query(Order, Buyer, Supplier, SupplierApplication)
        .join(Buyer, Buyer.id == Order.buyer_id)
        .join(Supplier, Supplier.id == Order.supplier_id)
        .outerjoin(SupplierApplication, SupplierApplication.user_id == Supplier.id)
        .filter(ownership)
    )
    if status is not None:
        query = query.filter(Order.status == status)
    total = query.count()
    rows = (
        query.order_by(Order.created_at.desc(), Order.id.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
        .all()
    )
    return rows, total


def get_order(
    db: Session,
    user: User,
    order_id: int,
    *,
    scope: str,
) -> tuple[Order, User, User, SupplierApplication | None, list[OrderEvent]]:
    order = _owned_order(db, user, order_id, scope=scope)
    buyer = db.get(User, order.buyer_id)
    supplier = db.get(User, order.supplier_id)
    application = db.query(SupplierApplication).filter(
        SupplierApplication.user_id == order.supplier_id
    ).first()
    events = db.query(OrderEvent).filter(
        OrderEvent.order_id == order.id
    ).order_by(OrderEvent.created_at.asc(), OrderEvent.id.asc()).all()
    return order, buyer, supplier, application, events


def confirm_order(
    db: Session,
    user: User,
    order_id: int,
    *,
    scope: str,
    version: int,
    note: str | None,
) -> tuple[Order, bool]:
    order = _owned_order(db, user, order_id, scope=scope, lock=True)
    confirmation_field = (
        "supplier_confirmed_at" if scope == "supplier" else "buyer_confirmed_at"
    )
    if getattr(order, confirmation_field) is not None:
        return order, True
    _check_version(order, version)
    if order.status != "pending_confirmation":
        raise ApiError("ORDER_NOT_CONFIRMABLE", "当前订单不能确认", 409)
    if order.payment_status not in ("not_required", "paid"):
        raise ApiError("ORDER_PAYMENT_REQUIRED", "买家完成支付后商家才能确认订单", 409)
    now = _now()
    setattr(order, confirmation_field, now)
    previous = order.status
    if order.buyer_confirmed_at is not None and order.supplier_confirmed_at is not None:
        if not can_transition(ORDER_TRANSITIONS, order.status, "confirmed"):
            raise ApiError("ORDER_NOT_CONFIRMABLE", "当前订单不能确认", 409)
        order.status = "confirmed"
        order.confirmed_at = now
    order.version += 1
    _event(
        db,
        order,
        user,
        event_type=f"{scope}_confirmed",
        from_status=previous,
        to_status=order.status,
        note=note,
    )
    _notify_counterparty(db, order, user, "订单确认状态已更新", f"订单 {order.order_no} 的一方已完成确认。")
    _commit(db)
    db.refresh(order)
    return order, False


def cancel_order(
    db: Session,
    user: User,
    order_id: int,
    *,
    scope: str,
    version: int,
    reason: str,
) -> Order:
    order = _owned_order(db, user, order_id, scope=scope, lock=True)
    _check_version(order, version)
    if not can_transition(ORDER_TRANSITIONS, order.status, "cancelled"):
        raise ApiError("ORDER_NOT_CANCELLABLE", "交付开始后不能直接取消，请联系平台处理", 409)
    previous = order.status
    order.status = "cancelled"
    order.cancelled_at = _now()
    order.cancelled_by_user_id = user.id
    order.cancel_reason = reason
    order.version += 1
    _event(
        db,
        order,
        user,
        event_type="order_cancelled",
        from_status=previous,
        to_status="cancelled",
        note=reason,
        extra={"cancelled_by": scope},
    )
    _notify_counterparty(db, order, user, "订单已取消", f"订单 {order.order_no} 已取消：{reason}")
    request = db.query(BuyRequest).filter(
        BuyRequest.id == order.buy_request_id
    ).with_for_update().first()
    if request is not None and can_transition(BUY_REQUEST_TRANSITIONS, request.status, "closed"):
        request_previous = request.status
        request.status = "closed"
        request.closed_at = order.cancelled_at
        request.close_reason = f"关联订单已取消：{reason}"
        request.version += 1
        db.add(BuyRequestEvent(
            buy_request_id=request.id,
            actor_user_id=user.id,
            actor_role=user.role,
            event_type="order_cancelled",
            from_status=request_previous,
            to_status="closed",
            payload={"order_id": order.id, "order_no": order.order_no},
        ))
    resource_service.release_for_order(db, order.id, f"订单取消：{reason}")
    _commit(db)
    db.refresh(order)
    return order


def start_delivery(
    db: Session,
    user: User,
    order_id: int,
    *,
    version: int,
    note: str | None,
) -> Order:
    order = _owned_order(db, user, order_id, scope="supplier", lock=True)
    _validate_delivery_note(note)
    _check_version(order, version)
    if not can_transition(ORDER_TRANSITIONS, order.status, "delivering"):
        raise ApiError("ORDER_NOT_DELIVERABLE", "订单必须先完成双方确认", 409)
    previous = order.status
    order.status = "delivering"
    order.delivery_started_at = _now()
    order.delivery_note = note
    order.version += 1
    resource_service.allocate_for_order(db, order.id)
    _event(
        db,
        order,
        user,
        event_type="delivery_started",
        from_status=previous,
        to_status="delivering",
        note=note,
    )
    _notify_counterparty(db, order, user, "订单开始交付", f"订单 {order.order_no} 已进入交付阶段。")
    _commit(db)
    db.refresh(order)
    return order


def mark_delivered(
    db: Session,
    user: User,
    order_id: int,
    *,
    version: int,
    note: str | None,
) -> Order:
    order = _owned_order(db, user, order_id, scope="supplier", lock=True)
    _validate_delivery_note(note)
    _check_version(order, version)
    if not can_transition(ORDER_TRANSITIONS, order.status, "delivered"):
        raise ApiError("ORDER_NOT_DELIVERING", "订单尚未进入交付中状态", 409)
    previous = order.status
    order.status = "delivered"
    order.delivered_at = _now()
    order.delivery_note = note
    order.version += 1
    _event(
        db,
        order,
        user,
        event_type="delivery_marked_delivered",
        from_status=previous,
        to_status="delivered",
        note=note,
    )
    _notify_counterparty(db, order, user, "订单等待验收", f"订单 {order.order_no} 已标记交付完成，请及时验收。")
    _commit(db)
    db.refresh(order)
    return order


def complete_order(
    db: Session,
    user: User,
    order_id: int,
    *,
    version: int,
    note: str | None,
) -> Order:
    order = _owned_order(db, user, order_id, scope="buyer", lock=True)
    _check_version(order, version)
    if not can_transition(ORDER_TRANSITIONS, order.status, "completed"):
        raise ApiError("ORDER_NOT_COMPLETABLE", "商家标记已交付后才能确认完成", 409)
    previous = order.status
    order.status = "completed"
    order.completed_at = _now()
    order.version += 1
    _event(
        db,
        order,
        user,
        event_type="buyer_completed",
        from_status=previous,
        to_status="completed",
        note=note,
    )
    _notify_counterparty(db, order, user, "订单已完成", f"订单 {order.order_no} 已由买家确认完成。")
    request = db.query(BuyRequest).filter(
        BuyRequest.id == order.buy_request_id
    ).with_for_update().first()
    if request is not None and can_transition(BUY_REQUEST_TRANSITIONS, request.status, "completed"):
        request_previous = request.status
        request.status = "completed"
        request.version += 1
        db.add(BuyRequestEvent(
            buy_request_id=request.id,
            actor_user_id=user.id,
            actor_role=user.role,
            event_type="order_completed",
            from_status=request_previous,
            to_status="completed",
            payload={"order_id": order.id, "order_no": order.order_no},
        ))
    _commit(db)
    db.refresh(order)
    return order
