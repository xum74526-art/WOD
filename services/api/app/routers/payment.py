from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse, PlainTextResponse
from sqlalchemy.orm import Session

from app.core.deps import get_current_platform, get_current_user
from app.db.session import get_db
from app.models.user import User
from app.schemas.payment import RechargePaymentCreateIn
from app.services.mapay import (
    checkout_html,
    create_recharge_order,
    handle_notification,
    payment_status,
    public_config,
    query_provider_and_reconcile,
    get_owned_order,
)
from app.utils.response import BizError, success
from app.services.auth_session import normalize_platform
from app.services.trade_mode import recharge_enabled, require_recharge_enabled


router = APIRouter(prefix="/api/payments/mapay", tags=["payment"])


@router.get("/config")
def payment_config(user: User = Depends(get_current_user)):
    config = public_config()
    config["enabled"] = bool(config.get("enabled") and recharge_enabled())
    return success(config)


@router.post("/recharge-orders")
def create_payment(
    data: RechargePaymentCreateIn,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
    platform: str = Depends(get_current_platform),
):
    require_recharge_enabled()
    return success(
        create_recharge_order(
            db,
            user.id,
            data.amount_cny,
            payment_type=data.payment_type,
            created_platform=normalize_platform(platform),
        )
    )


@router.get("/orders/{order_no}")
def get_payment(
    order_no: str,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    return success(payment_status(db, user.id, order_no))


@router.post("/orders/{order_no}/query")
def query_payment(
    order_no: str,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    return success(query_provider_and_reconcile(db, get_owned_order(db, user.id, order_no)))


@router.get("/checkout/{token}", response_class=HTMLResponse)
def checkout(token: str, db: Session = Depends(get_db)):
    response = HTMLResponse(checkout_html(db, token))
    response.headers["Cache-Control"] = "no-store"
    response.headers["Referrer-Policy"] = "no-referrer"
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    return response


async def _notification_params(request: Request) -> dict:
    params = dict(request.query_params)
    if request.method == "POST":
        form = await request.form()
        params.update({str(key): str(value) for key, value in form.items()})
    return params


async def _notify(request: Request, db: Session):
    try:
        awaitable_params = await _notification_params(request)
        handle_notification(db, awaitable_params)
        return PlainTextResponse("success")
    except BizError:
        db.rollback()
        return PlainTextResponse("fail", status_code=400)


@router.get("/notify", response_class=PlainTextResponse)
async def notify_get(request: Request, db: Session = Depends(get_db)):
    return await _notify(request, db)


@router.post("/notify", response_class=PlainTextResponse)
async def notify_post(request: Request, db: Session = Depends(get_db)):
    return await _notify(request, db)
