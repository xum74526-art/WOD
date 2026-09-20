from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.core.deps import get_current_platform, get_current_user
from app.db.session import get_db
from app.models.user import User
from app.models.withdrawal import WithdrawalOrder
from app.schemas.withdrawal import WithdrawalCreateIn
from app.services.manual_payout import (
    ALL_WITHDRAWAL_STATUSES,
    cancel_withdrawal,
    create_withdrawal,
    order_out,
    withdrawal_config,
)
from app.utils.response import BizError, success
from app.services.auth_session import normalize_platform
from app.services.trade_mode import require_withdrawal_enabled


router = APIRouter(prefix="/api/withdrawals", tags=["withdrawal"])


@router.get("/config")
def config(user: User = Depends(get_current_user)):
    return success(withdrawal_config())


@router.post("")
def create(
    data: WithdrawalCreateIn,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
    platform: str = Depends(get_current_platform),
):
    require_withdrawal_enabled()
    order = create_withdrawal(
        db,
        user,
        amount_card_hours=data.amount_card_hours,
        bank_card_id=data.bank_card_id,
        client_request_id=data.client_request_id,
        created_platform=normalize_platform(platform),
    )
    return success(order_out(db, order))


@router.get("")
def list_orders(
    status_filter: str | None = None,
    page: int = 1,
    page_size: int = 20,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    if page < 1 or page_size < 1 or page_size > 100:
        raise BizError("分页参数无效")
    if status_filter and status_filter not in ALL_WITHDRAWAL_STATUSES:
        raise BizError("提现状态无效")
    query = db.query(WithdrawalOrder).filter(WithdrawalOrder.user_id == user.id)
    if status_filter:
        query = query.filter(WithdrawalOrder.status == status_filter)
    total = query.count()
    rows = query.order_by(WithdrawalOrder.created_at.desc(), WithdrawalOrder.id.desc()).offset(
        (page - 1) * page_size
    ).limit(page_size).all()
    return success({
        "total": total,
        "page": page,
        "page_size": page_size,
        "items": [order_out(db, row) for row in rows],
    })


def _user_order(db: Session, user_id: int, order_id: int) -> WithdrawalOrder:
    order = db.query(WithdrawalOrder).filter(
        WithdrawalOrder.id == order_id,
        WithdrawalOrder.user_id == user_id,
    ).first()
    if not order:
        raise BizError("提现申请不存在", status_code=404)
    return order


@router.get("/{order_id}")
def detail(
    order_id: int,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    return success(order_out(db, _user_order(db, user.id, order_id)))


@router.post("/{order_id}/cancel")
def cancel(
    order_id: int,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
    platform: str = Depends(get_current_platform),
):
    order = _user_order(db, user.id, order_id)
    cancel_withdrawal(db, order, user, platform=normalize_platform(platform))
    db.refresh(order)
    return success(order_out(db, order))
