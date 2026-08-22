from decimal import Decimal

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.core.deps import get_current_user
from app.db.session import get_db
from app.models.offline_purchase import OfflinePurchase
from app.models.user import User
from app.schemas.offline_purchase import OfflinePurchaseIn, OfflinePurchaseOut
from app.utils.response import BizError, success

router = APIRouter(prefix="/api/offline-purchases", tags=["offline-purchase"])


@router.get("")
def list_purchases(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    items = db.query(OfflinePurchase).filter(
        OfflinePurchase.user_id == user.id
    ).order_by(OfflinePurchase.created_at.desc()).all()
    return success([OfflinePurchaseOut.model_validate(p).model_dump() for p in items])


@router.post("")
def submit_purchase(
    data: OfflinePurchaseIn,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    if data.quantity <= 0:
        raise BizError("数量必须大于 0")
    if data.budget < 0:
        raise BizError("预算不能为负")
    p = OfflinePurchase(
        user_id=user.id,
        device_model=data.device_model,
        quantity=data.quantity,
        budget=Decimal(str(data.budget)),
        contact=data.contact,
        phone=data.phone,
        remark=data.remark,
    )
    db.add(p)
    db.commit()
    db.refresh(p)
    return success(OfflinePurchaseOut.model_validate(p).model_dump())
