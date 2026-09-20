from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse, PlainTextResponse
from sqlalchemy.orm import Session

from app.core.deps import get_current_platform, get_current_user
from app.core.config import settings
from app.core.rate_limit import limit_payment_callback, limit_payment_query
from app.db.session import get_db
from app.models.user import User
from app.schemas.payment import RechargePaymentCreateIn
from app.services.mapay import (
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
    config["enabled"] = False
    config["new_collection_retired"] = True
    config["legacy_reconciliation_enabled"] = bool(
        settings.MAPAY_LEGACY_RECONCILIATION_ENABLED
    )
    return success(config)


@router.post("/recharge-orders", include_in_schema=False)
def create_payment(
    data: RechargePaymentCreateIn,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
    platform: str = Depends(get_current_platform),
):
    raise BizError(
        "MaPay 已停止创建新充值订单，请使用七相支付",
        status_code=410,
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
    limit_payment_query(user.id)
    return success(query_provider_and_reconcile(db, get_owned_order(db, user.id, order_no)))


@router.get("/checkout/{token}", response_class=HTMLResponse, include_in_schema=False)
def checkout(token: str, db: Session = Depends(get_db)):
    raise BizError("MaPay 新收银台已停用；历史订单仅支持查询", status_code=410)


async def _notification_params(request: Request) -> dict:
    params = dict(request.query_params)
    if request.method == "POST":
        form = await request.form()
        params.update({str(key): str(value) for key, value in form.items()})
    return params


async def _notify(request: Request, db: Session):
    try:
        limit_payment_callback("mapay")
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
