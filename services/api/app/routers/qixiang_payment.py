from fastapi import APIRouter, Depends, Query, Request
from fastapi.responses import PlainTextResponse, RedirectResponse
from sqlalchemy.orm import Session

from app.core.deps import get_current_platform, get_current_user
from app.core.rate_limit import (
    limit_payment_callback,
    limit_payment_checkout,
    limit_payment_create,
    limit_payment_query,
)
from app.db.session import get_db
from app.models.user import User
from app.schemas.payment import RechargePaymentCreateIn
from app.services import mapay as legacy_mapay
from app.services.qixiangpay import (
    PROVIDER,
    cancel_recharge_order,
    checkout_redirect_url,
    create_recharge_order,
    get_owned_order,
    handle_notification,
    list_owned_payment_orders,
    payment_status,
    public_config,
    query_provider_and_reconcile,
    resolve_checkout_client_ip,
)
from app.utils.response import BizError, success
from app.services.auth_session import normalize_platform
from app.services.trade_mode import recharge_enabled, require_recharge_enabled


router = APIRouter(prefix="/api/payments/qixiang", tags=["payment"])
# Keep the historical KAI prefix available while existing Web/App builds drain.
# Both prefixes operate on the same qixiangpay rows and accounting boundary.
legacy_router = APIRouter(
    prefix="/api/payments/qixiangpay",
    tags=["payment-legacy"],
    include_in_schema=False,
)


@router.get("/config")
@legacy_router.get("/config")
def payment_config(user: User = Depends(get_current_user)):
    config = public_config()
    config["enabled"] = bool(config.get("enabled") and recharge_enabled())
    return success(config)


@router.post("/recharge-orders")
@legacy_router.post("/recharge-orders")
def create_payment(
    data: RechargePaymentCreateIn,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
    platform: str = Depends(get_current_platform),
):
    limit_payment_create(user.id)
    require_recharge_enabled()
    return success(
        create_recharge_order(
            db,
            user.id,
            data.amount_cny,
            payment_type=data.payment_type,
            created_platform=normalize_platform(platform),
            client_request_id=data.client_request_id,
        )
    )


@router.get("/orders")
@legacy_router.get("/orders")
def list_payments(
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=50),
    status: str | None = Query(default=None, max_length=24),
    order_no: str | None = Query(default=None, max_length=40),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    return success(
        list_owned_payment_orders(
            db,
            user.id,
            page=page,
            page_size=page_size,
            status=status,
            order_no=order_no,
        )
    )


@router.get("/orders/{order_no}")
@legacy_router.get("/orders/{order_no}")
def get_payment(
    order_no: str,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    return success(payment_status(db, user.id, order_no))


@router.post("/orders/{order_no}/query")
@legacy_router.post("/orders/{order_no}/query")
def query_payment(
    order_no: str,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    limit_payment_query(user.id)
    order = get_owned_order(db, user.id, order_no)
    if order.provider == legacy_mapay.PROVIDER:
        return success(legacy_mapay.query_provider_and_reconcile(db, order))
    return success(query_provider_and_reconcile(db, order))


@router.post("/orders/{order_no}/cancel")
@legacy_router.post("/orders/{order_no}/cancel")
def cancel_payment(
    order_no: str,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
    platform: str = Depends(get_current_platform),
):
    limit_payment_query(user.id)
    order = get_owned_order(db, user.id, order_no)
    if order.provider != PROVIDER:
        raise BizError("历史充值订单不能通过七相支付网关取消", status_code=409)
    return success(cancel_recharge_order(db, order, platform=normalize_platform(platform)))


@router.get("/checkout/{token}", response_class=RedirectResponse, status_code=303)
@legacy_router.get("/checkout/{token}", response_class=RedirectResponse, status_code=303)
def checkout(token: str, request: Request, db: Session = Depends(get_db)):
    limit_payment_checkout(token)
    client_ip = resolve_checkout_client_ip(
        request.client.host if request.client else None,
        x_real_ip=request.headers.get("x-real-ip"),
        x_forwarded_for=request.headers.get("x-forwarded-for"),
    )
    response = RedirectResponse(
        checkout_redirect_url(db, token, client_ip=client_ip),
        status_code=303,
    )
    response.headers["Cache-Control"] = "no-store"
    response.headers["Referrer-Policy"] = "no-referrer"
    response.headers["X-Content-Type-Options"] = "nosniff"
    return response


async def _notification_params(request: Request) -> dict:
    params = dict(request.query_params)
    if request.method == "POST":
        form = await request.form()
        params.update({str(key): str(value) for key, value in form.items()})
    return params


async def _notify(request: Request, db: Session):
    try:
        limit_payment_callback(PROVIDER)
        handle_notification(db, await _notification_params(request))
        return PlainTextResponse("success")
    except BizError:
        db.rollback()
        return PlainTextResponse("fail", status_code=400)


@router.get("/notify", response_class=PlainTextResponse)
@legacy_router.get("/notify", response_class=PlainTextResponse)
async def notify_get(request: Request, db: Session = Depends(get_db)):
    return await _notify(request, db)


@router.post("/notify", response_class=PlainTextResponse)
@legacy_router.post("/notify", response_class=PlainTextResponse)
async def notify_post(request: Request, db: Session = Depends(get_db)):
    return await _notify(request, db)
