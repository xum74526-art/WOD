from decimal import Decimal
from typing import Literal

from fastapi import APIRouter, Depends, Query
from sqlalchemy import or_
from sqlalchemy.orm import Session

from app.core.deps import get_current_platform, get_current_user, require_admin
from app.core.rate_limit import limit_admin_coupon_action, limit_coupon_redeem
from app.db.session import get_db
from app.models.coupon import Coupon
from app.models.user import User
from app.schemas.coupon import (
    CouponCampaignCreateIn,
    CouponCampaignCreatedOut,
    CouponCampaignStatusIn,
    RedeemIn,
)
from app.services.coupon_service import (
    campaign_output,
    coupon_output,
    create_campaign,
    eligible_coupons,
    list_campaigns,
    redeem_code,
    update_campaign_status,
    utc_now,
)
from app.utils.response import success


router = APIRouter(prefix="/api/coupons", tags=["coupon"])
admin_router = APIRouter(prefix="/api/admin/coupon-campaigns", tags=["admin-coupon"])


@router.get("")
def list_coupons(
    status: Literal["available", "used", "expired"] | None = None,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    now = utc_now()
    query = db.query(Coupon).filter(Coupon.user_id == user.id)
    if status == "available":
        query = query.filter(
            Coupon.status == "available",
            or_(Coupon.expires_at.is_(None), Coupon.expires_at >= now),
        )
    elif status == "used":
        query = query.filter(Coupon.status == "used")
    elif status == "expired":
        query = query.filter(or_(
            Coupon.status == "expired",
            (Coupon.status == "available") & (Coupon.expires_at < now),
        ))
    items = query.order_by(Coupon.created_at.desc(), Coupon.id.desc()).all()
    return success([coupon_output(item, now) for item in items])


@router.post("/redeem")
def redeem(
    data: RedeemIn,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
    platform: str = Depends(get_current_platform),
):
    limit_coupon_redeem(user.id)
    coupon = redeem_code(
        db,
        user_id=user.id,
        code=data.code,
        platform=platform,
    )
    return success(coupon_output(coupon))


@router.get("/available")
def available_coupons(
    amount: Decimal | None = Query(default=None, ge=0),
    product_id: int | None = Query(default=None, ge=1),
    purchase_type: Literal["usage", "holding"] = "usage",
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    items = eligible_coupons(
        db,
        user_id=user.id,
        amount=amount,
        product_id=product_id,
        purchase_type=purchase_type,
    )
    return success([coupon_output(item) for item in items])


@admin_router.get("")
def admin_list_coupon_campaigns(
    status: Literal["active", "scheduled", "disabled", "expired", "exhausted"] | None = None,
    keyword: str | None = Query(default=None, max_length=64),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    _admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    return success(list_campaigns(
        db,
        status=status,
        keyword=keyword,
        page=page,
        page_size=page_size,
    ))


@admin_router.post("")
def admin_create_coupon_campaign(
    data: CouponCampaignCreateIn,
    admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
    platform: str = Depends(get_current_platform),
):
    limit_admin_coupon_action(admin.id)
    campaign, code = create_campaign(
        db,
        data=data,
        actor_user_id=admin.id,
        platform=platform,
    )
    payload = campaign_output(campaign)
    payload["code"] = code
    return success(CouponCampaignCreatedOut.model_validate(payload).model_dump())


@admin_router.post("/{campaign_id}/status")
def admin_update_coupon_campaign_status(
    campaign_id: int,
    data: CouponCampaignStatusIn,
    admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    limit_admin_coupon_action(admin.id)
    campaign = update_campaign_status(
        db,
        campaign_id=campaign_id,
        status=data.status,
        expected_version=data.expected_version,
        actor_user_id=admin.id,
    )
    return success(campaign_output(campaign))
