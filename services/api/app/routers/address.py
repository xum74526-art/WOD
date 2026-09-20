from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.core.deps import get_current_user
from app.db.session import get_db
from app.models.address import Address
from app.models.user import User
from app.schemas.address import AddressIn, AddressOut, AddressUpdate
from app.utils.response import BizError, success

router = APIRouter(prefix="/api/addresses", tags=["address"])


def _clear_defaults(user: User, db: Session) -> None:
    db.query(Address).filter(Address.user_id == user.id).update({"is_default": False})


def _get_owned(cid: int, user: User, db: Session) -> Address:
    a = db.query(Address).filter(Address.id == cid, Address.user_id == user.id).first()
    if not a:
        raise BizError("地址不存在", status_code=404)
    return a


@router.get("")
def list_addresses(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    items = db.query(Address).filter(Address.user_id == user.id).order_by(
        Address.is_default.desc(), Address.created_at.desc()
    ).all()
    return success([AddressOut.model_validate(a).model_dump() for a in items])


@router.post("")
def add_address(
    data: AddressIn,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    if data.is_default:
        _clear_defaults(user, db)
    a = Address(
        user_id=user.id,
        name=data.name,
        phone=data.phone,
        province=data.province,
        city=data.city,
        district=data.district,
        detail=data.detail,
        label=data.label,
        is_default=data.is_default,
    )
    db.add(a)
    db.commit()
    db.refresh(a)
    return success(AddressOut.model_validate(a).model_dump())


@router.put("/{aid}")
def update_address(
    aid: int,
    data: AddressUpdate,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    a = _get_owned(aid, user, db)
    payload = data.model_dump(exclude_unset=True)
    if payload.get("is_default") is True:
        _clear_defaults(user, db)
    for k, v in payload.items():
        setattr(a, k, v)
    db.commit()
    db.refresh(a)
    return success(AddressOut.model_validate(a).model_dump())


@router.delete("/{aid}")
def delete_address(
    aid: int,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    a = _get_owned(aid, user, db)
    db.delete(a)
    db.commit()
    return success({"id": aid, "deleted": True})


@router.post("/{aid}/default")
def set_default(
    aid: int,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    a = _get_owned(aid, user, db)
    _clear_defaults(user, db)
    a.is_default = True
    db.commit()
    return success({"id": aid, "is_default": True})
