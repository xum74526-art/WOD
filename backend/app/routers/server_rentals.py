from typing import Annotated

from fastapi import APIRouter, Depends, Header, Query, Request, Response, status
from sqlalchemy.orm import Session

from app.db import get_db
from app.models import Order, PaymentIntent, User
from app.responses import ok
from app.security import get_current_user, require_admin, require_admin_csrf, require_csrf
from app.server_rental_schemas import (
    LeaseRenewIn,
    LeaseSweepIn,
    LocalRefundCompleteIn,
    RefundInitiateIn,
    SshKeyCreateIn,
    SshKeyUpdateIn,
)
from app.services import server_rentals as service


router = APIRouter(prefix="/api/v1", tags=["server-rentals"])


def _private(response: Response) -> None:
    response.headers["Cache-Control"] = "no-store"


@router.get("/account/ssh-keys")
def list_ssh_keys(
    response: Response,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    _private(response)
    rows = service.list_ssh_keys(db, user)
    return ok([service.ssh_key_out(row) for row in rows], {
        "private_keys_accepted": False,
        "usage": "server_login_only",
    })


@router.post("/account/ssh-keys", status_code=status.HTTP_201_CREATED)
def create_ssh_key(
    data: SshKeyCreateIn,
    response: Response,
    user: User = Depends(require_csrf),
    db: Session = Depends(get_db),
):
    _private(response)
    return ok(service.ssh_key_out(service.create_ssh_key(db, user, data)))


@router.patch("/account/ssh-keys/{key_id}")
def update_ssh_key(
    key_id: int,
    data: SshKeyUpdateIn,
    response: Response,
    user: User = Depends(require_csrf),
    db: Session = Depends(get_db),
):
    _private(response)
    return ok(service.ssh_key_out(service.update_ssh_key(db, user, key_id, data)))


@router.delete("/account/ssh-keys/{key_id}")
def revoke_ssh_key(
    key_id: int,
    version: Annotated[int, Query(ge=1)],
    response: Response,
    user: User = Depends(require_csrf),
    db: Session = Depends(get_db),
):
    _private(response)
    return ok(service.ssh_key_out(service.revoke_ssh_key(db, user, key_id, version)))


@router.get("/account/leases")
def list_buyer_leases(
    response: Response,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    _private(response)
    rows = service.list_leases(db, user, scope="buyer")
    return ok([
        service.lease_out(lease, order, product, key, buyer_view=True)
        for lease, order, product, key in rows
    ], {"renewal_grace_hours": 2, "payment_mode": service.payment_mode()})


@router.post("/account/leases/{lease_id}/renew")
def renew_lease(
    lease_id: int,
    data: LeaseRenewIn,
    request: Request,
    response: Response,
    idempotency_key: str = Header(min_length=16, max_length=64, alias="Idempotency-Key"),
    user: User = Depends(require_csrf),
    db: Session = Depends(get_db),
):
    _private(response)
    lease, order, product, key, intent, replay = service.renew_lease(
        db,
        user,
        lease_id,
        data,
        idempotency_key=idempotency_key,
        client_ip=request.client.host if request.client else "127.0.0.1",
    )
    data = service.lease_out(lease, order, product, key, buyer_view=True)
    data["payment"] = {
        "payment_no": intent.payment_no,
        "status": intent.status,
        "provider": intent.provider,
        "checkout_url": intent.checkout_url,
    }
    return ok(data, {
        "idempotent_replay": replay,
        "payment_mode": intent.provider,
    })


@router.get("/supplier/servers")
def list_supplier_servers(
    response: Response,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    _private(response)
    rows = service.list_supplier_servers(db, user)
    return ok([service.server_out(server, product) for server, product in rows], {
        "production_agent_auth": "Ed25519 device signatures; optional mTLS proxy enforcement",
        "local_agent_mode": "simulator",
    })


@router.get("/supplier/leases")
def list_supplier_leases(
    response: Response,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    _private(response)
    rows = service.list_leases(db, user, scope="supplier")
    return ok([
        service.lease_out(lease, order, product, key, buyer_view=False)
        for lease, order, product, key in rows
    ], {"buyer_connection_details_exposed": False})


@router.post("/admin/server-leases/sweep")
def sweep_due_leases(
    data: LeaseSweepIn,
    response: Response,
    _: User = Depends(require_admin_csrf),
    db: Session = Depends(get_db),
):
    _private(response)
    return ok(service.process_due_leases(db))


@router.get("/admin/refunds")
def list_refunds(
    response: Response,
    refund_status: str | None = Query(default=None, alias="status", max_length=24),
    _: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    _private(response)
    rows = service.list_refunds(db, status=refund_status)
    return ok([service.refund_out(row, order, intent) for row, order, intent in rows])


@router.post("/admin/refunds/{refund_id}/initiate")
def initiate_refund(
    refund_id: int,
    data: RefundInitiateIn,
    response: Response,
    admin: User = Depends(require_admin_csrf),
    db: Session = Depends(get_db),
):
    _private(response)
    row = service.initiate_refund(
        db,
        admin,
        refund_id,
        version=data.version,
        note=data.note,
    )
    order = db.get(Order, row.order_id)
    intent = db.get(PaymentIntent, row.payment_intent_id)
    return ok(service.refund_out(row, order, intent))


@router.post("/admin/refunds/{refund_id}/complete")
def complete_local_refund(
    refund_id: int,
    data: LocalRefundCompleteIn,
    response: Response,
    admin: User = Depends(require_admin_csrf),
    db: Session = Depends(get_db),
):
    """Complete only the built-in local test payment; Ping++ refunds finish by Webhook."""
    _private(response)
    row = service.complete_local_refund(
        db,
        admin,
        refund_id,
        version=data.version,
        provider_reference=data.provider_reference,
        note=data.note,
    )
    order = db.get(Order, row.order_id)
    intent = db.get(PaymentIntent, row.payment_intent_id)
    return ok(service.refund_out(row, order, intent))
