from datetime import datetime, timedelta
from decimal import Decimal

from fastapi import APIRouter, Depends
from sqlalchemy import or_
from sqlalchemy.orm import Session

from app.core.deps import get_current_user
from app.db.session import get_db
from app.models.coupon import Coupon
from app.models.user import User
from app.schemas.coupon import CouponOut, RedeemIn
from app.utils.response import BizError, success

router = APIRouter(prefix="/api/coupons", tags=["coupon"])


# MVP：兑换码到券模板的简单映射。
_COUPON_CODES = {
    "WOD10": {"name": "10卡时优惠券", "amount": Decimal("10"), "min_amount": Decimal("100")},
    "WOD50": {"name": "50卡时优惠券", "amount": Decimal("50"), "min_amount": Decimal("500")},
    # 兼容已经发出的旧品牌兑换码。
    "XOD10": {"name": "10卡时优惠券", "amount": Decimal("10"), "min_amount": Decimal("100")},
    "XOD50": {"name": "50卡时优惠券", "amount": Decimal("50"), "min_amount": Decimal("500")},
    "NEW88": {"name": "新人88卡时券", "amount": Decimal("88"), "min_amount": Decimal("888")},
}

_COUPON_TTL_DAYS = 30


def _now() -> datetime:
    return datetime.now()


def _is_expired(c: Coupon) -> bool:
    return c.expires_at is not None and c.expires_at < _now()


@router.get("")
def list_coupons(
    status: str | None = None,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    q = db.query(Coupon).filter(Coupon.user_id == user.id)
    now = _now()
    if status == "available":
        q = q.filter(
            Coupon.status == "available",
            or_(Coupon.expires_at.is_(None), Coupon.expires_at >= now),
        )
    elif status == "used":
        q = q.filter(Coupon.status == "used")
    elif status == "expired":
        q = q.filter(
            or_(Coupon.status == "expired",
                (Coupon.status == "available") & (Coupon.expires_at < now))
        )
    items = q.order_by(Coupon.created_at.desc()).all()
    return success([CouponOut.model_validate(c).model_dump() for c in items])


@router.post("/redeem")
def redeem(
    data: RedeemIn,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    tpl = _COUPON_CODES.get(data.code.strip().upper())
    if not tpl:
        raise BizError("兑换码无效")
    # 同一用户同一券名只允许兑换一次，防止重复领取。
    existed = db.query(Coupon).filter(
        Coupon.user_id == user.id, Coupon.name == tpl["name"]
    ).first()
    if existed:
        raise BizError("您已兑换过该优惠券")
    c = Coupon(
        user_id=user.id,
        name=tpl["name"],
        amount=tpl["amount"],
        min_amount=tpl["min_amount"],
        status="available",
        expires_at=_now() + timedelta(days=_COUPON_TTL_DAYS),
    )
    db.add(c)
    db.commit()
    db.refresh(c)
    return success(CouponOut.model_validate(c).model_dump())


@router.get("/available")
def available_coupons(
    amount: float | None = None,
    product_id: int | None = None,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    now = _now()
    q = db.query(Coupon).filter(
        Coupon.user_id == user.id,
        Coupon.status == "available",
        or_(Coupon.expires_at.is_(None), Coupon.expires_at >= now),
    )
    items = q.order_by(Coupon.amount.desc()).all()
    # 按订单金额过滤满减门槛；amount 未传则返回全部可用券。product_id 当前忽略（MVP）。
    if amount is not None:
        items = [c for c in items if c.min_amount <= Decimal(str(amount))]
    return success([CouponOut.model_validate(c).model_dump() for c in items])
