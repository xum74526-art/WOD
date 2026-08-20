from decimal import Decimal
from math import ceil
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, Query, Response, status
from sqlalchemy.orm import Session

from app.buy_request_schemas import (
    BuyRequestCreateIn,
    BuyRequestUpdateIn,
    CloseBuyRequestIn,
    ExtendBuyRequestIn,
    VersionedActionIn,
)
from app.db import get_db
from app.models import BuyRequestContact, CloudComputeRequestDetail, User
from app.responses import ok
from app.security import get_current_user, require_csrf
from app.services import buy_requests as service

router = APIRouter(prefix="/api/v1", tags=["buy-requests"])
RequestStatus = Literal[
    "draft", "reviewing", "published", "negotiating", "matched", "completed", "closed", "expired", "rejected"
]
PublicStatus = Literal["published", "negotiating"]
PublicSort = Literal["latest", "deadline", "budget"]


def _private(response: Response) -> None:
    response.headers["Cache-Control"] = "no-store"


def _page_meta(page: int, page_size: int, total: int) -> dict:
    return {
        "page": page,
        "page_size": page_size,
        "total": total,
        "total_pages": ceil(total / page_size) if total else 0,
    }


@router.post("/buy-requests", status_code=status.HTTP_201_CREATED)
def create_buy_request(
    data: BuyRequestCreateIn,
    response: Response,
    user: User = Depends(require_csrf),
    db: Session = Depends(get_db),
):
    _private(response)
    row = service.create_request(db, user, data)
    detail = db.get(CloudComputeRequestDetail, row.id)
    contact = db.get(BuyRequestContact, row.id)
    return ok(service.request_out(row, private=True, detail=detail, contact=contact, events=[]))


@router.get("/account/buy-requests")
def list_account_buy_requests(
    response: Response,
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int, Query(ge=1, le=100)] = 20,
    request_status: Annotated[RequestStatus | None, Query(alias="status")] = None,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    _private(response)
    rows, total = service.list_owned_requests(
        db, user, page=page, page_size=page_size, status=request_status
    )
    return ok(
        [service.request_out(row, private=True) for row in rows],
        _page_meta(page, page_size, total),
    )


@router.get("/account/buy-requests/{request_id}")
def get_account_buy_request(
    request_id: int,
    response: Response,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    _private(response)
    row, detail, contact, events = service.get_owned_request(db, user, request_id)
    return ok(service.request_out(
        row, private=True, detail=detail, contact=contact, events=events
    ))


@router.patch("/account/buy-requests/{request_id}")
def update_account_buy_request(
    request_id: int,
    data: BuyRequestUpdateIn,
    response: Response,
    user: User = Depends(require_csrf),
    db: Session = Depends(get_db),
):
    _private(response)
    service.update_request(db, user, request_id, data)
    row, detail, contact, events = service.get_owned_request(db, user, request_id)
    return ok(service.request_out(
        row, private=True, detail=detail, contact=contact, events=events
    ))


@router.delete("/account/buy-requests/{request_id}")
def delete_account_buy_request(
    request_id: int,
    response: Response,
    version: Annotated[int, Query(ge=1)],
    user: User = Depends(require_csrf),
    db: Session = Depends(get_db),
):
    _private(response)
    service.delete_request(db, user, request_id, version)
    return ok({"deleted": True})


@router.post("/account/buy-requests/{request_id}/publish")
def publish_account_buy_request(
    request_id: int,
    data: VersionedActionIn,
    response: Response,
    user: User = Depends(require_csrf),
    db: Session = Depends(get_db),
):
    _private(response)
    row = service.publish_request(db, user, request_id, data.version)
    return ok(service.request_out(row, private=True))


@router.post("/account/buy-requests/{request_id}/close")
def close_account_buy_request(
    request_id: int,
    data: CloseBuyRequestIn,
    response: Response,
    user: User = Depends(require_csrf),
    db: Session = Depends(get_db),
):
    _private(response)
    row = service.close_request(
        db, user, request_id, version=data.version, reason=data.reason
    )
    return ok(service.request_out(row, private=True))


@router.post("/account/buy-requests/{request_id}/extend")
def extend_account_buy_request(
    request_id: int,
    data: ExtendBuyRequestIn,
    response: Response,
    user: User = Depends(require_csrf),
    db: Session = Depends(get_db),
):
    _private(response)
    row = service.extend_request(
        db,
        user,
        request_id,
        version=data.version,
        quote_deadline_at=data.quote_deadline_at,
    )
    return ok(service.request_out(row, private=True))


@router.get("/public/buy-requests")
def list_public_buy_requests(
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int, Query(ge=1, le=100)] = 20,
    gpu_model: Annotated[str | None, Query(min_length=1, max_length=64)] = None,
    region: Annotated[str | None, Query(min_length=2, max_length=32)] = None,
    min_quantity: Annotated[int | None, Query(ge=1)] = None,
    max_budget: Annotated[Decimal | None, Query(ge=0)] = None,
    currency: Annotated[
        str | None,
        Query(min_length=3, max_length=8, pattern=r"^[A-Z0-9_]+$"),
    ] = None,
    request_status: Annotated[PublicStatus | None, Query(alias="status")] = None,
    sort: PublicSort = "latest",
    db: Session = Depends(get_db),
):
    rows, total = service.list_public_requests(
        db,
        page=page,
        page_size=page_size,
        gpu_model=gpu_model,
        region=region,
        min_quantity=min_quantity,
        max_budget=max_budget,
        currency=currency,
        status=request_status,
        sort=sort,
    )
    return ok(
        [service.request_out(row, private=False) for row in rows],
        _page_meta(page, page_size, total),
    )


@router.get("/public/buy-requests/{request_no}")
def get_public_buy_request(request_no: str, db: Session = Depends(get_db)):
    row, detail = service.get_public_request(db, request_no)
    return ok(service.request_out(row, private=False, detail=detail))
