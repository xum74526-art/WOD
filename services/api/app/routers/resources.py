from math import ceil
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, Query, Response, status
from sqlalchemy.orm import Session

from app.db import get_db
from app.models import Order, Product, User
from app.resource_schemas import (
    ReservationReleaseIn,
    ResourceCreateIn,
    ResourceRejectIn,
    ResourceReviewIn,
    ResourceUpdateIn,
)
from app.responses import ok
from app.security import (
    get_current_user,
    require_admin,
    require_admin_action,
    require_authenticated_action,
)
from app.services import resources as service


router = APIRouter(prefix="/api/v1", tags=["resources"])
ResourceStatus = Literal["draft", "pending_review", "approved", "published", "rejected", "archived"]
ReservationStatus = Literal["reserved", "allocated", "released"]


def _private(response: Response) -> None:
    response.headers["Cache-Control"] = "no-store"


def _meta(page: int, page_size: int, total: int) -> dict:
    return {
        "page": page,
        "page_size": page_size,
        "total": total,
        "total_pages": ceil(total / page_size) if total else 0,
    }


@router.get("/supplier/resources")
def list_supplier_resources(
    response: Response,
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int, Query(ge=1, le=100)] = 20,
    resource_status: Annotated[ResourceStatus | None, Query(alias="status")] = None,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    _private(response)
    rows, total = service.list_supplier_resources(
        db, user, page=page, page_size=page_size, status=resource_status
    )
    return ok([service.resource_out(db, row) for row in rows], _meta(page, page_size, total))


@router.post("/supplier/resources", status_code=status.HTTP_201_CREATED)
def create_supplier_resource(
    data: ResourceCreateIn,
    response: Response,
    user: User = Depends(require_authenticated_action),
    db: Session = Depends(get_db),
):
    _private(response)
    return ok(service.resource_out(db, service.create_resource(db, user, data)))


@router.get("/supplier/resources/{resource_id}")
def get_supplier_resource(
    resource_id: int,
    response: Response,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    _private(response)
    row = service.get_supplier_resource(db, user, resource_id)
    return ok({
        "resource": service.resource_out(db, row),
        "price_versions": [
            service.price_version_out(item)
            for item in service.price_versions(db, user, row.id)
        ],
        "events": [service.review_event_out(item) for item in service.review_events(db, row.id)],
    })


@router.patch("/supplier/resources/{resource_id}")
def update_supplier_resource(
    resource_id: int,
    data: ResourceUpdateIn,
    response: Response,
    user: User = Depends(require_authenticated_action),
    db: Session = Depends(get_db),
):
    _private(response)
    return ok(service.resource_out(db, service.update_resource(db, user, resource_id, data)))


@router.delete("/supplier/resources/{resource_id}")
def delete_supplier_resource(
    resource_id: int,
    response: Response,
    version: Annotated[int, Query(ge=1)],
    user: User = Depends(require_authenticated_action),
    db: Session = Depends(get_db),
):
    _private(response)
    service.delete_resource(db, user, resource_id, version)
    return ok({"deleted": True})


def _supplier_transition(
    response: Response,
    db: Session,
    user: User,
    resource_id: int,
    action: str,
    data: ResourceReviewIn,
):
    _private(response)
    row = service.transition_supplier_resource(
        db,
        user,
        resource_id,
        action=action,
        version=data.version,
        note=data.note,
    )
    return ok(service.resource_out(db, row))


@router.post("/supplier/resources/{resource_id}/submit-review")
def submit_resource_review(resource_id: int, data: ResourceReviewIn, response: Response, user: User = Depends(require_authenticated_action), db: Session = Depends(get_db)):
    return _supplier_transition(response, db, user, resource_id, "submit-review", data)


@router.post("/supplier/resources/{resource_id}/withdraw-review")
def withdraw_resource_review(resource_id: int, data: ResourceReviewIn, response: Response, user: User = Depends(require_authenticated_action), db: Session = Depends(get_db)):
    return _supplier_transition(response, db, user, resource_id, "withdraw-review", data)


@router.post("/supplier/resources/{resource_id}/publish")
def publish_resource(resource_id: int, data: ResourceReviewIn, response: Response, user: User = Depends(require_authenticated_action), db: Session = Depends(get_db)):
    return _supplier_transition(response, db, user, resource_id, "publish", data)


@router.post("/supplier/resources/{resource_id}/unpublish")
def unpublish_resource(resource_id: int, data: ResourceReviewIn, response: Response, user: User = Depends(require_authenticated_action), db: Session = Depends(get_db)):
    return _supplier_transition(response, db, user, resource_id, "unpublish", data)


@router.get("/supplier/inventory-reservations")
def list_inventory_reservations(
    response: Response,
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int, Query(ge=1, le=100)] = 20,
    reservation_status: Annotated[ReservationStatus | None, Query(alias="status")] = None,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    _private(response)
    rows, total = service.list_reservations(
        db, user, page=page, page_size=page_size, status=reservation_status
    )
    return ok(
        [service.reservation_out(row, product, order) for row, product, order in rows],
        _meta(page, page_size, total),
    )


@router.post("/supplier/inventory-reservations/{reservation_id}/release")
def release_inventory_reservation(
    reservation_id: int,
    data: ReservationReleaseIn,
    response: Response,
    user: User = Depends(require_authenticated_action),
    db: Session = Depends(get_db),
):
    _private(response)
    row = service.release_reservation(
        db, user, reservation_id, version=data.version, reason=data.reason
    )
    product = db.get(Product, row.product_id)
    order = db.get(Order, row.order_id)
    return ok(service.reservation_out(row, product, order))


@router.get("/admin/resources")
def list_admin_resources(
    response: Response,
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int, Query(ge=1, le=100)] = 20,
    resource_status: Annotated[ResourceStatus | None, Query(alias="status")] = None,
    search: Annotated[str | None, Query(min_length=1, max_length=100)] = None,
    admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    _private(response)
    rows, total = service.list_admin_resources(
        db, page=page, page_size=page_size, status=resource_status, search=search
    )
    return ok([
        {
            **service.resource_out(db, row),
            "supplier": {
                "display_name": supplier.display_name,
                "company_name": application.company_name if application else None,
            },
        }
        for row, supplier, application in rows
    ], _meta(page, page_size, total))


def _review(
    response: Response,
    db: Session,
    admin: User,
    resource_id: int,
    action: str,
    data: ResourceReviewIn | ResourceRejectIn,
):
    _private(response)
    row = service.review_resource(
        db,
        admin,
        resource_id,
        action=action,
        version=data.version,
        note=data.note,
    )
    return ok(service.resource_out(db, row))


@router.post("/admin/resources/{resource_id}/approve")
def approve_resource(resource_id: int, data: ResourceReviewIn, response: Response, admin: User = Depends(require_admin_action), db: Session = Depends(get_db)):
    return _review(response, db, admin, resource_id, "approve", data)


@router.post("/admin/resources/{resource_id}/reject")
def reject_resource(resource_id: int, data: ResourceRejectIn, response: Response, admin: User = Depends(require_admin_action), db: Session = Depends(get_db)):
    return _review(response, db, admin, resource_id, "reject", data)
