from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.core.deps import get_current_user
from app.db.session import get_db
from app.models.onboarding import ComputeOnboarding
from app.models.user import User
from app.models.verification import Verification
from app.schemas.onboarding import OnboardingIn, OnboardingOut
from app.utils.response import BizError, success

router = APIRouter(prefix="/api/onboarding", tags=["onboarding"])

_VALID_ENTITY_TYPES = {"personal", "company"}


@router.get("/mine")
def my_onboardings(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    items = db.query(ComputeOnboarding).filter(
        ComputeOnboarding.user_id == user.id
    ).order_by(ComputeOnboarding.created_at.desc()).all()
    return success([OnboardingOut.model_validate(o).model_dump() for o in items])


@router.post("")
def submit_onboarding(
    data: OnboardingIn,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    if data.entity_type not in _VALID_ENTITY_TYPES:
        raise BizError("主体类型只能是 personal 或 company")
    if data.device_count <= 0:
        raise BizError("设备数量必须大于 0")
    if data.entity_type == "personal":
        verification = db.query(Verification).filter(
            Verification.user_id == user.id,
            Verification.status == "verified",
        ).first()
        if not verification:
            raise BizError("个人设备托管前请先完成实名认证", status_code=403)
    elif user.supplier_status != "approved":
        raise BizError("企业设备托管仅对已认证商家开放", status_code=403)
    o = ComputeOnboarding(
        user_id=user.id,
        entity_type=data.entity_type,
        contact=data.contact,
        phone=data.phone,
        device_model=data.device_model,
        device_count=data.device_count,
        location=data.location,
        remark=data.remark,
    )
    db.add(o)
    db.commit()
    db.refresh(o)
    return success(OnboardingOut.model_validate(o).model_dump())
