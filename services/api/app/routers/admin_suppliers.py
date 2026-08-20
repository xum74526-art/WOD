from math import ceil
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, Query, Response
from sqlalchemy.orm import Session

from app.db import get_db
from app.models import User
from app.responses import ok
from app.schemas import SupplierApprovalIn, SupplierRejectionIn
from app.security import require_admin, require_admin_action
from app.services import supplier_applications as service

router = APIRouter(prefix="/api/v1/admin/supplier-applications", tags=["admin-suppliers"])
ApplicationStatus = Literal["pending", "approved", "rejected"]


def _private(response: Response) -> None:
    response.headers["Cache-Control"] = "no-store"


def _page_meta(page: int, page_size: int, total: int) -> dict:
    return {
        "page": page,
        "page_size": page_size,
        "total": total,
        "total_pages": ceil(total / page_size) if total else 0,
    }


@router.get("")
def list_supplier_applications(
    response: Response,
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int, Query(ge=1, le=100)] = 20,
    application_status: Annotated[
        ApplicationStatus | None,
        Query(alias="status"),
    ] = None,
    search: Annotated[str | None, Query(min_length=1, max_length=100)] = None,
    admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    _private(response)
    rows, total = service.list_applications(
        db,
        page=page,
        page_size=page_size,
        status=application_status,
        search=search,
    )
    return ok(
        [
            service.application_out(
                application,
                applicant=applicant,
                include_reviewer=True,
            )
            for application, applicant in rows
        ],
        _page_meta(page, page_size, total),
    )


@router.get("/{application_id}")
def get_supplier_application(
    application_id: int,
    response: Response,
    admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    _private(response)
    application, applicant, events = service.get_application(db, application_id)
    return ok({
        "application": service.application_out(
            application,
            applicant=applicant,
            include_reviewer=True,
        ),
        "events": [service.event_out(event) for event in events],
    })


@router.post("/{application_id}/approve")
def approve_supplier_application(
    application_id: int,
    data: SupplierApprovalIn,
    response: Response,
    admin: User = Depends(require_admin_action),
    db: Session = Depends(get_db),
):
    _private(response)
    application, applicant, replay = service.approve_application(
        db,
        admin,
        application_id,
        version=data.version,
        note=data.note,
    )
    return ok(
        service.application_out(
            application,
            applicant=applicant,
            include_reviewer=True,
        ),
        {"idempotent_replay": replay},
    )


@router.post("/{application_id}/reject")
def reject_supplier_application(
    application_id: int,
    data: SupplierRejectionIn,
    response: Response,
    admin: User = Depends(require_admin_action),
    db: Session = Depends(get_db),
):
    _private(response)
    application, applicant, replay = service.reject_application(
        db,
        admin,
        application_id,
        version=data.version,
        note=data.note,
    )
    return ok(
        service.application_out(
            application,
            applicant=applicant,
            include_reviewer=True,
        ),
        {"idempotent_replay": replay},
    )
