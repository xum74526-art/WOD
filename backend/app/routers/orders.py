from math import ceil
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, Header, Query, Request, Response, status
from sqlalchemy.orm import Session

from app.db import get_db
from app.models import BuyerSshKey, Product, User
from app.order_schemas import (
    OrderCancelIn,
    OrderCompleteIn,
    OrderConfirmIn,
    OrderDeliveryIn,
)
from app.responses import ok
from app.security import get_current_user, require_csrf
from app.services import orders as service
from app.server_rental_schemas import DirectServerRentalIn
from app.services import server_rentals


router = APIRouter(prefix="/api/v1", tags=["orders"])
OrderStatus = Literal[
    "pending_confirmation",
    "confirmed",
    "delivering",
    "delivered",
    "completed",
    "cancelled",
]


def _private(response: Response) -> None:
    response.headers["Cache-Control"] = "no-store"


def _page_meta(page: int, page_size: int, total: int) -> dict:
    return {
        "page": page,
        "page_size": page_size,
        "total": total,
        "total_pages": ceil(total / page_size) if total else 0,
    }


def _list(
    response: Response,
    user: User,
    db: Session,
    *,
    scope: str,
    page: int,
    page_size: int,
    status: str | None,
):
    _private(response)
    rows, total = service.list_orders(
        db,
        user,
        scope=scope,
        page=page,
        page_size=page_size,
        status=status,
    )
    return ok(
        [
            service.order_out(
                order,
                scope=scope,
                buyer=buyer,
                supplier=supplier,
                application=application,
            )
            for order, buyer, supplier, application in rows
        ],
        _page_meta(page, page_size, total),
    )


@router.get("/account/orders")
def list_account_orders(
    response: Response,
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int, Query(ge=1, le=100)] = 20,
    order_status: Annotated[OrderStatus | None, Query(alias="status")] = None,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    return _list(
        response,
        user,
        db,
        scope="buyer",
        page=page,
        page_size=page_size,
        status=order_status,
    )


@router.get("/supplier/orders")
def list_supplier_orders(
    response: Response,
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int, Query(ge=1, le=100)] = 20,
    order_status: Annotated[OrderStatus | None, Query(alias="status")] = None,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    return _list(
        response,
        user,
        db,
        scope="supplier",
        page=page,
        page_size=page_size,
        status=order_status,
    )


def _detail(response: Response, user: User, db: Session, order_id: int, scope: str):
    _private(response)
    order, buyer, supplier, application, events = service.get_order(
        db, user, order_id, scope=scope
    )
    return ok(service.order_out(
        order,
        scope=scope,
        buyer=buyer,
        supplier=supplier,
        application=application,
        events=events,
    ))


@router.post("/account/orders/direct", status_code=status.HTTP_201_CREATED)
def create_direct_order(
    data: DirectServerRentalIn,
    request: Request,
    response: Response,
    idempotency_key: str = Header(min_length=16, max_length=64, alias="Idempotency-Key"),
    user: User = Depends(require_csrf),
    db: Session = Depends(get_db),
):
    _private(response)
    order, lease, intent, replay = server_rentals.create_direct_rental(
        db,
        user,
        data,
        idempotency_key=idempotency_key,
        client_ip=request.client.host if request.client else "127.0.0.1",
    )
    key = db.get(BuyerSshKey, lease.ssh_key_id)
    product = db.get(Product, order.product_id)
    return ok({
        "order": service.order_summary_out(order),
        "lease": server_rentals.lease_out(lease, order, product, key, buyer_view=True),
        "payment": {
            "payment_no": intent.payment_no,
            "status": intent.status,
            "provider": intent.provider,
            "checkout_url": intent.checkout_url,
        },
    }, {"idempotent_replay": replay, "payment_mode": intent.provider})


@router.get("/account/orders/{order_id}")
def get_account_order(
    order_id: int,
    response: Response,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    return _detail(response, user, db, order_id, "buyer")


@router.get("/supplier/orders/{order_id}")
def get_supplier_order(
    order_id: int,
    response: Response,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    return _detail(response, user, db, order_id, "supplier")


def _confirm(
    response: Response,
    user: User,
    db: Session,
    order_id: int,
    data: OrderConfirmIn,
    scope: str,
):
    _private(response)
    order, replay = service.confirm_order(
        db,
        user,
        order_id,
        scope=scope,
        version=data.version,
        note=data.note,
    )
    return ok(service.order_summary_out(order), {"idempotent_replay": replay})


@router.post("/account/orders/{order_id}/confirm")
def confirm_account_order(
    order_id: int,
    data: OrderConfirmIn,
    response: Response,
    user: User = Depends(require_csrf),
    db: Session = Depends(get_db),
):
    return _confirm(response, user, db, order_id, data, "buyer")


@router.post("/supplier/orders/{order_id}/confirm")
def confirm_supplier_order(
    order_id: int,
    data: OrderConfirmIn,
    response: Response,
    user: User = Depends(require_csrf),
    db: Session = Depends(get_db),
):
    return _confirm(response, user, db, order_id, data, "supplier")


def _cancel(
    response: Response,
    user: User,
    db: Session,
    order_id: int,
    data: OrderCancelIn,
    scope: str,
):
    _private(response)
    order = service.cancel_order(
        db,
        user,
        order_id,
        scope=scope,
        version=data.version,
        reason=data.reason,
    )
    return ok(service.order_summary_out(order))


@router.post("/account/orders/{order_id}/cancel")
def cancel_account_order(
    order_id: int,
    data: OrderCancelIn,
    response: Response,
    user: User = Depends(require_csrf),
    db: Session = Depends(get_db),
):
    return _cancel(response, user, db, order_id, data, "buyer")


@router.post("/supplier/orders/{order_id}/cancel")
def cancel_supplier_order(
    order_id: int,
    data: OrderCancelIn,
    response: Response,
    user: User = Depends(require_csrf),
    db: Session = Depends(get_db),
):
    return _cancel(response, user, db, order_id, data, "supplier")


@router.post("/supplier/orders/{order_id}/start-delivery")
def start_supplier_delivery(
    order_id: int,
    data: OrderDeliveryIn,
    response: Response,
    user: User = Depends(require_csrf),
    db: Session = Depends(get_db),
):
    _private(response)
    return ok(service.order_summary_out(service.start_delivery(
        db, user, order_id, version=data.version, note=data.note
    )))


@router.post("/supplier/orders/{order_id}/mark-delivered")
def mark_supplier_delivered(
    order_id: int,
    data: OrderDeliveryIn,
    response: Response,
    user: User = Depends(require_csrf),
    db: Session = Depends(get_db),
):
    _private(response)
    return ok(service.order_summary_out(service.mark_delivered(
        db, user, order_id, version=data.version, note=data.note
    )))


@router.post("/account/orders/{order_id}/complete")
def complete_account_order(
    order_id: int,
    data: OrderCompleteIn,
    response: Response,
    user: User = Depends(require_csrf),
    db: Session = Depends(get_db),
):
    _private(response)
    return ok(service.order_summary_out(service.complete_order(
        db, user, order_id, version=data.version, note=data.note
    )))
