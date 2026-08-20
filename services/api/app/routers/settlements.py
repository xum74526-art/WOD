from typing import Annotated, Literal

from fastapi import APIRouter, Depends, Header, Query, Response, status
from sqlalchemy.orm import Session

from app.db import get_db
from app.models import User
from app.responses import ok
from app.security import get_current_user, require_admin, require_admin_action, require_authenticated_action
from app.services import settlements as service
from app.settlement_schemas import (
    SupplierWithdrawalCreateIn,
    WithdrawalCompleteIn,
    WithdrawalRejectIn,
    WithdrawalReviewIn,
)


router = APIRouter(prefix="/api/v1", tags=["settlements"])
WithdrawalStatus = Literal["requested", "approved", "rejected", "paid", "cancelled"]


def _private(response: Response) -> None:
    response.headers["Cache-Control"] = "no-store"


@router.get("/supplier/revenue")
def supplier_revenue(
    response: Response,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    _private(response)
    return ok(service.revenue_snapshot(db, user), {
        "real_data_only": True,
        "settlement_mode": "manual_bank_transfer",
    })


@router.get("/supplier/settlements")
def supplier_settlements(
    response: Response,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    _private(response)
    rows = service.list_supplier_withdrawals(db, user)
    return ok([service.withdrawal_out(row) for row in rows if row.status == "paid"])


@router.get("/supplier/withdrawals")
def supplier_withdrawals(
    response: Response,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    _private(response)
    return ok([
        service.withdrawal_out(row)
        for row in service.list_supplier_withdrawals(db, user)
    ])


@router.post("/supplier/withdrawals", status_code=status.HTTP_201_CREATED)
def create_supplier_withdrawal(
    data: SupplierWithdrawalCreateIn,
    response: Response,
    idempotency_key: Annotated[str, Header(min_length=16, max_length=64, alias="Idempotency-Key")],
    user: User = Depends(require_authenticated_action),
    db: Session = Depends(get_db),
):
    _private(response)
    row = service.create_withdrawal(db, user, data, idempotency_key=idempotency_key)
    return ok(service.withdrawal_out(row))


@router.post("/supplier/withdrawals/{withdrawal_id}/cancel")
def cancel_supplier_withdrawal(
    withdrawal_id: int,
    data: WithdrawalReviewIn,
    response: Response,
    user: User = Depends(require_authenticated_action),
    db: Session = Depends(get_db),
):
    _private(response)
    return ok(service.withdrawal_out(
        service.cancel_withdrawal(db, user, withdrawal_id, version=data.version)
    ))


@router.get("/admin/withdrawals")
def admin_withdrawals(
    response: Response,
    withdrawal_status: Annotated[WithdrawalStatus | None, Query(alias="status")] = None,
    admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    _private(response)
    return ok([
        {
            **service.withdrawal_out(row, reveal_account=True),
            "supplier": {
                "display_name": supplier.display_name,
                "email": supplier.email,
                "company_name": application.company_name if application else None,
            },
        }
        for row, supplier, application in service.list_admin_withdrawals(
            db, status=withdrawal_status
        )
    ])


@router.post("/admin/withdrawals/{withdrawal_id}/approve")
def approve_withdrawal(
    withdrawal_id: int,
    data: WithdrawalReviewIn,
    response: Response,
    admin: User = Depends(require_admin_action),
    db: Session = Depends(get_db),
):
    _private(response)
    return ok(service.withdrawal_out(service.approve_withdrawal(
        db, admin, withdrawal_id, version=data.version, note=data.note
    ), reveal_account=True))


@router.post("/admin/withdrawals/{withdrawal_id}/reject")
def reject_withdrawal(
    withdrawal_id: int,
    data: WithdrawalRejectIn,
    response: Response,
    admin: User = Depends(require_admin_action),
    db: Session = Depends(get_db),
):
    _private(response)
    return ok(service.withdrawal_out(service.reject_withdrawal(
        db, admin, withdrawal_id, version=data.version, note=data.note
    ), reveal_account=True))


@router.post("/admin/withdrawals/{withdrawal_id}/complete")
def complete_withdrawal(
    withdrawal_id: int,
    data: WithdrawalCompleteIn,
    response: Response,
    admin: User = Depends(require_admin_action),
    db: Session = Depends(get_db),
):
    _private(response)
    return ok(service.withdrawal_out(service.complete_withdrawal(
        db,
        admin,
        withdrawal_id,
        version=data.version,
        payment_reference=data.payment_reference,
        note=data.note,
    ), reveal_account=True))
