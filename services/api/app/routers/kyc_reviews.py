from typing import Annotated, Literal

from fastapi import APIRouter, Depends, Query, Response
from sqlalchemy.orm import Session

from app.db import get_db
from app.kyc_schemas import ManualKycRejectIn, ManualKycReviewIn
from app.models import User
from app.responses import ok
from app.security import require_admin, require_admin_action
from app.services import manual_kyc


router = APIRouter(prefix="/api/v1/admin/kyc", tags=["admin-kyc"])
KycStatus = Literal["pending", "approved", "rejected"]


def _private(response: Response) -> None:
    response.headers["Cache-Control"] = "no-store"


@router.get("")
def list_kyc_reviews(
    response: Response,
    review_status: Annotated[KycStatus | None, Query(alias="status")] = None,
    _: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    _private(response)
    return ok([
        manual_kyc.application_out(row, applicant=user, reveal_identifier=True)
        for row, user in manual_kyc.list_pending(db, status=review_status)
    ])


@router.post("/{application_id}/approve")
def approve_kyc(
    application_id: int,
    data: ManualKycReviewIn,
    response: Response,
    admin: User = Depends(require_admin_action),
    db: Session = Depends(get_db),
):
    _private(response)
    row = manual_kyc.review(
        db, admin, application_id, version=data.version, approved=True, note=data.note
    )
    applicant = db.get(User, row.user_id)
    return ok(manual_kyc.application_out(row, applicant=applicant, reveal_identifier=True))


@router.post("/{application_id}/reject")
def reject_kyc(
    application_id: int,
    data: ManualKycRejectIn,
    response: Response,
    admin: User = Depends(require_admin_action),
    db: Session = Depends(get_db),
):
    _private(response)
    row = manual_kyc.review(
        db, admin, application_id, version=data.version, approved=False, note=data.note
    )
    applicant = db.get(User, row.user_id)
    return ok(manual_kyc.application_out(row, applicant=applicant, reveal_identifier=True))
