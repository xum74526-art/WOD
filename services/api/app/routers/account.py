from fastapi import APIRouter, Depends, Response
from sqlalchemy.orm import Session

from app.db import get_db
from app.models import AccessLease, BuyRequest, Order, SupplierApplication, User
from app.providers import integration_descriptors
from app.responses import ok
from app.schemas import AccountProfileUpdateIn, SupplierApplicationIn
from app.security import get_current_user, get_optional_user, require_authenticated_action
from app.services import supplier_applications as application_service
from app.services import manual_kyc

router = APIRouter(prefix="/api/v1", tags=["account"])


def _private(response: Response) -> None:
    response.headers["Cache-Control"] = "no-store"


@router.get("/account/summary")
def account_summary(
    response: Response,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    _private(response)
    application = db.query(SupplierApplication).filter(SupplierApplication.user_id == user.id).first()
    request_count = db.query(BuyRequest).filter(
        BuyRequest.buyer_id == user.id,
        BuyRequest.status.in_(("draft", "reviewing", "published", "negotiating")),
    ).count()
    active_order_count = db.query(Order).filter(
        Order.buyer_id == user.id,
        Order.status.in_(("pending_confirmation", "confirmed", "delivering", "delivered")),
    ).count()
    active_asset_count = db.query(AccessLease).filter(
        AccessLease.buyer_id == user.id,
        AccessLease.status.in_(("pending_authorization", "active", "grace")),
    ).count()
    integrations = integration_descriptors()
    return ok({
        "user": {
            "id": user.id,
            "display_name": user.display_name,
            "role": user.role,
            "email": user.email,
            "email_verified": user.email_verified,
        },
        "metrics": {
            "active_orders": active_order_count,
            "active_assets": active_asset_count,
            "hosted_devices": 0,
            "open_requests": request_count,
        },
        "supplier_status": application.status if application else "not_applied",
        "services": {
            "payment": integrations["payment"]["configured"],
            "kyc": manual_kyc.provider_descriptor()["configured"],
            "object_storage": integrations["object_storage"]["configured"],
        },
    }, {"real_data_only": True})


@router.patch("/account/profile")
def update_account_profile(
    data: AccountProfileUpdateIn,
    response: Response,
    user: User = Depends(require_authenticated_action),
    db: Session = Depends(get_db),
):
    _private(response)
    user.display_name = data.display_name
    db.commit()
    db.refresh(user)
    return ok({
        "id": user.id,
        "display_name": user.display_name,
        "email": user.email,
        "email_verified": user.email_verified,
        "phone": user.phone,
        "phone_verified": user.phone_verified,
        "role": user.role,
    })


@router.get("/supplier/application")
def supplier_application(
    response: Response,
    user: User | None = Depends(get_optional_user),
    db: Session = Depends(get_db),
):
    _private(response)
    if not user:
        return ok({"status": "auth_required"})
    row = db.query(SupplierApplication).filter(SupplierApplication.user_id == user.id).first()
    if not row:
        return ok({"status": "not_applied"})
    return ok({
        "id": row.id,
        "company_name": row.company_name,
        "contact_name": row.contact_name,
        "contact_phone": row.contact_phone[:3] + "****" + row.contact_phone[-4:],
        "region": row.region,
        "description": row.description,
        "status": row.status,
        "review_note": row.review_note,
        "reviewed_at": row.reviewed_at,
        "created_at": row.created_at,
        "updated_at": row.updated_at,
        "version": row.version,
    })


@router.post("/supplier/application")
def submit_supplier_application(
    data: SupplierApplicationIn,
    response: Response,
    user: User = Depends(require_authenticated_action),
    db: Session = Depends(get_db),
):
    _private(response)
    row = application_service.submit_application(db, user, data)
    return ok({"id": row.id, "status": row.status, "version": row.version})
