from math import ceil
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, Query, Response, status
from sqlalchemy.orm import Session

from app.db import get_db
from app.models import User
from app.quote_schemas import (
    QuoteAcceptIn,
    QuoteCreateIn,
    QuoteDecisionIn,
    QuoteUpdateIn,
    QuoteVersionedActionIn,
    QuoteWithdrawIn,
)
from app.responses import ok
from app.security import get_current_user, require_authenticated_action
from app.services import quotes as service

router = APIRouter(prefix="/api/v1", tags=["quotes"])
QuoteStatus = Literal[
    "draft", "submitted", "shortlisted", "accepted", "rejected", "withdrawn", "expired"
]
BuyerQuoteStatus = Literal[
    "submitted", "shortlisted", "accepted", "rejected", "withdrawn", "expired"
]
SupplierRequestStatus = Literal["published", "negotiating"]
SupplierRequestSort = Literal["latest", "deadline", "budget"]


def _private(response: Response) -> None:
    response.headers["Cache-Control"] = "no-store"


def _page_meta(page: int, page_size: int, total: int) -> dict:
    return {
        "page": page,
        "page_size": page_size,
        "total": total,
        "total_pages": ceil(total / page_size) if total else 0,
    }


@router.get("/supplier/buy-requests")
def list_supplier_buy_requests(
    response: Response,
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int, Query(ge=1, le=100)] = 20,
    gpu_model: Annotated[str | None, Query(min_length=1, max_length=64)] = None,
    region: Annotated[str | None, Query(min_length=2, max_length=32)] = None,
    request_status: Annotated[
        SupplierRequestStatus | None,
        Query(alias="status"),
    ] = None,
    sort: SupplierRequestSort = "latest",
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    _private(response)
    rows, total = service.list_supplier_requests(
        db,
        user,
        page=page,
        page_size=page_size,
        gpu_model=gpu_model,
        region=region,
        status=request_status,
        sort=sort,
    )
    return ok(
        [service.supplier_request_summary_out(row) for row in rows],
        _page_meta(page, page_size, total),
    )


@router.get("/supplier/buy-requests/{request_id}")
def get_supplier_buy_request(
    request_id: int,
    response: Response,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    _private(response)
    request, detail, quotes = service.get_supplier_request(db, user, request_id)
    return ok(service.supplier_request_out(request, detail, quotes))


@router.post(
    "/supplier/buy-requests/{request_id}/quotes",
    status_code=status.HTTP_201_CREATED,
)
def create_supplier_quote(
    request_id: int,
    data: QuoteCreateIn,
    response: Response,
    user: User = Depends(require_authenticated_action),
    db: Session = Depends(get_db),
):
    _private(response)
    quote = service.create_quote(db, user, request_id, data)
    return ok(service.quote_out(quote))


@router.get("/supplier/quotes")
def list_supplier_quotes(
    response: Response,
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int, Query(ge=1, le=100)] = 20,
    quote_status: Annotated[QuoteStatus | None, Query(alias="status")] = None,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    _private(response)
    rows, total = service.list_supplier_quotes(
        db,
        user,
        page=page,
        page_size=page_size,
        status=quote_status,
    )
    return ok(
        [service.quote_out(quote, request=request) for quote, request in rows],
        _page_meta(page, page_size, total),
    )


@router.get("/supplier/quotes/{quote_id}")
def get_supplier_quote(
    quote_id: int,
    response: Response,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    _private(response)
    quote, request = service.get_supplier_quote(db, user, quote_id)
    return ok(service.quote_out(quote, request=request))


@router.patch("/supplier/quotes/{quote_id}")
def update_supplier_quote(
    quote_id: int,
    data: QuoteUpdateIn,
    response: Response,
    user: User = Depends(require_authenticated_action),
    db: Session = Depends(get_db),
):
    _private(response)
    quote = service.update_quote(db, user, quote_id, data)
    return ok(service.quote_out(quote))


@router.post("/supplier/quotes/{quote_id}/submit")
def submit_supplier_quote(
    quote_id: int,
    data: QuoteVersionedActionIn,
    response: Response,
    user: User = Depends(require_authenticated_action),
    db: Session = Depends(get_db),
):
    _private(response)
    quote = service.submit_quote(db, user, quote_id, data.version)
    return ok(service.quote_out(quote))


@router.post("/supplier/quotes/{quote_id}/withdraw")
def withdraw_supplier_quote(
    quote_id: int,
    data: QuoteWithdrawIn,
    response: Response,
    user: User = Depends(require_authenticated_action),
    db: Session = Depends(get_db),
):
    _private(response)
    quote = service.withdraw_quote(
        db,
        user,
        quote_id,
        version=data.version,
        reason=data.reason,
    )
    return ok(service.quote_out(quote))


@router.get("/account/buy-requests/{request_id}/quotes")
def list_account_buy_request_quotes(
    request_id: int,
    response: Response,
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int, Query(ge=1, le=100)] = 20,
    quote_status: Annotated[BuyerQuoteStatus | None, Query(alias="status")] = None,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    _private(response)
    request, rows, total = service.list_buyer_quotes(
        db,
        user,
        request_id,
        page=page,
        page_size=page_size,
        status=quote_status,
    )
    return ok(
        {
            "request": service.request_summary(request),
            "quotes": [
                service.quote_out(
                    quote,
                    supplier=supplier,
                    application=application,
                )
                for quote, supplier, application in rows
            ],
        },
        _page_meta(page, page_size, total),
    )


@router.post("/account/buy-requests/{request_id}/quotes/{quote_id}/shortlist")
def shortlist_account_quote(
    request_id: int,
    quote_id: int,
    data: QuoteDecisionIn,
    response: Response,
    user: User = Depends(require_authenticated_action),
    db: Session = Depends(get_db),
):
    _private(response)
    quote = service.shortlist_quote(
        db,
        user,
        request_id,
        quote_id,
        quote_version=data.quote_version,
        note=data.note,
    )
    return ok(service.quote_out(quote))


@router.post("/account/buy-requests/{request_id}/quotes/{quote_id}/reject")
def reject_account_quote(
    request_id: int,
    quote_id: int,
    data: QuoteDecisionIn,
    response: Response,
    user: User = Depends(require_authenticated_action),
    db: Session = Depends(get_db),
):
    _private(response)
    quote = service.reject_quote(
        db,
        user,
        request_id,
        quote_id,
        quote_version=data.quote_version,
        note=data.note,
    )
    return ok(service.quote_out(quote))


@router.post("/account/buy-requests/{request_id}/quotes/{quote_id}/accept")
def accept_account_quote(
    request_id: int,
    quote_id: int,
    data: QuoteAcceptIn,
    response: Response,
    user: User = Depends(require_authenticated_action),
    db: Session = Depends(get_db),
):
    _private(response)
    order, replay = service.accept_quote(
        db,
        user,
        request_id,
        quote_id,
        request_version=data.request_version,
        quote_version=data.quote_version,
        note=data.note,
    )
    return ok(service.order_out(order), {"idempotent_replay": replay})
