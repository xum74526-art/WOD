"""Durable coupon issuance, redemption, order application, and restoration."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from decimal import Decimal
import hashlib
import hmac
import re
import secrets

from sqlalchemy import or_
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.config import settings
from app.models.coupon import Coupon, CouponCampaign
from app.models.ledger import Ledger
from app.models.order import Order
from app.models.product import Product
from app.models.wallet import Wallet
from app.schemas.coupon import CouponCampaignCreateIn, CouponCampaignOut, CouponOut
from app.services.auth_session import normalize_platform
from app.services.funding_allocation import funding_amount
from app.utils.response import BizError


_CODE_PATTERN = re.compile(r"[A-Z0-9]{8,32}")


def utc_now() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


def utc_naive(value: datetime | None) -> datetime | None:
    if value is None:
        return None
    if value.tzinfo is None:
        return value
    return value.astimezone(timezone.utc).replace(tzinfo=None)


def normalize_redemption_code(value: str) -> str:
    normalized = re.sub(r"[\s-]+", "", str(value or "")).upper()
    if not _CODE_PATTERN.fullmatch(normalized):
        raise BizError("兑换码无效", status_code=400)
    return normalized


def redemption_code_hash(value: str) -> str:
    normalized = normalize_redemption_code(value)
    return hmac.new(
        settings.SECRET_KEY.encode("utf-8"),
        f"coupon-code:{normalized}".encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()


def generate_redemption_code() -> str:
    alphabet = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"
    raw = "".join(secrets.choice(alphabet) for _ in range(16))
    return "KAI-" + "-".join(raw[index:index + 4] for index in range(0, 16, 4))


def effective_campaign_status(campaign: CouponCampaign, now: datetime | None = None) -> str:
    current = now or utc_now()
    if campaign.status == "disabled":
        return "disabled"
    if campaign.expires_at <= current:
        return "expired"
    if int(campaign.redeemed_count or 0) >= int(campaign.max_redemptions):
        return "exhausted"
    if campaign.starts_at is not None and campaign.starts_at > current:
        return "scheduled"
    return "active"


def effective_coupon_status(coupon: Coupon, now: datetime | None = None) -> str:
    if coupon.status == "available" and coupon.expires_at is not None:
        if coupon.expires_at < (now or utc_now()):
            return "expired"
    return coupon.status


def coupon_output(coupon: Coupon, now: datetime | None = None) -> dict:
    payload = CouponOut.model_validate(coupon).model_dump()
    payload["status"] = effective_coupon_status(coupon, now)
    return payload


def campaign_output(campaign: CouponCampaign, now: datetime | None = None) -> dict:
    payload = CouponCampaignOut.model_validate(campaign).model_dump()
    payload["status"] = effective_campaign_status(campaign, now)
    return payload


def _begin_sqlite_write(db: Session) -> None:
    if db.get_bind().dialect.name != "sqlite":
        return
    if db.in_transaction():
        db.rollback()
    db.connection().exec_driver_sql("BEGIN IMMEDIATE")


def create_campaign(
    db: Session,
    *,
    data: CouponCampaignCreateIn,
    actor_user_id: int,
    platform: str,
) -> tuple[CouponCampaign, str]:
    now = utc_now()
    starts_at = utc_naive(data.starts_at)
    expires_at = utc_naive(data.expires_at)
    if expires_at is None or expires_at <= now:
        raise BizError("兑换活动结束时间必须晚于当前时间", status_code=400)
    if starts_at is not None and expires_at <= starts_at:
        raise BizError("兑换活动结束时间必须晚于开始时间", status_code=400)
    if data.product_id is not None and db.query(Product.id).filter(
        Product.id == data.product_id
    ).first() is None:
        raise BizError("限定商品不存在", status_code=404)

    requested = data.code.strip() if data.code else None
    for _attempt in range(5):
        code = requested or generate_redemption_code()
        normalized = normalize_redemption_code(code)
        digest = redemption_code_hash(normalized)
        if db.query(CouponCampaign.id).filter(CouponCampaign.code_hash == digest).first():
            if requested:
                raise BizError("该兑换码已存在", status_code=409)
            continue
        campaign = CouponCampaign(
            code_hash=digest,
            code_hint=f"****{normalized[-4:]}",
            name=data.name,
            amount=funding_amount(data.amount),
            min_amount=funding_amount(data.min_amount),
            product_id=data.product_id,
            max_redemptions=data.max_redemptions,
            redeemed_count=0,
            coupon_ttl_days=data.coupon_ttl_days,
            status="active",
            starts_at=starts_at,
            expires_at=expires_at,
            created_by=actor_user_id,
            last_modified_by=actor_user_id,
            created_platform=normalize_platform(platform),
        )
        db.add(campaign)
        try:
            db.commit()
        except IntegrityError as exc:
            db.rollback()
            if requested:
                raise BizError("该兑换码已存在", status_code=409) from exc
            continue
        db.refresh(campaign)
        return campaign, code
    raise BizError("生成兑换码失败，请重试", status_code=409)


def list_campaigns(
    db: Session,
    *,
    status: str | None,
    keyword: str | None,
    page: int,
    page_size: int,
) -> dict:
    now = utc_now()
    query = db.query(CouponCampaign)
    if status == "active":
        query = query.filter(
            CouponCampaign.status == "active",
            CouponCampaign.expires_at > now,
            CouponCampaign.redeemed_count < CouponCampaign.max_redemptions,
            or_(CouponCampaign.starts_at.is_(None), CouponCampaign.starts_at <= now),
        )
    elif status == "scheduled":
        query = query.filter(
            CouponCampaign.status == "active",
            CouponCampaign.starts_at > now,
            CouponCampaign.expires_at > now,
            CouponCampaign.redeemed_count < CouponCampaign.max_redemptions,
        )
    elif status == "expired":
        query = query.filter(
            CouponCampaign.status == "active",
            CouponCampaign.expires_at <= now,
        )
    elif status == "exhausted":
        query = query.filter(
            CouponCampaign.status == "active",
            CouponCampaign.expires_at > now,
            CouponCampaign.redeemed_count >= CouponCampaign.max_redemptions
        )
    elif status == "disabled":
        query = query.filter(CouponCampaign.status == "disabled")
    normalized = str(keyword or "").strip()
    if normalized:
        query = query.filter(or_(
            CouponCampaign.name.contains(normalized),
            CouponCampaign.code_hint.contains(normalized[-4:]),
        ))
    total = query.count()
    rows = query.order_by(
        CouponCampaign.created_at.desc(), CouponCampaign.id.desc()
    ).offset((page - 1) * page_size).limit(page_size).all()
    return {
        "items": [campaign_output(row, now) for row in rows],
        "total": total,
        "page": page,
        "page_size": page_size,
    }


def update_campaign_status(
    db: Session,
    *,
    campaign_id: int,
    status: str,
    expected_version: int,
    actor_user_id: int,
) -> CouponCampaign:
    _begin_sqlite_write(db)
    campaign = db.query(CouponCampaign).filter(
        CouponCampaign.id == campaign_id
    ).with_for_update().first()
    if campaign is None:
        raise BizError("兑换活动不存在", status_code=404)
    if int(campaign.version or 1) != expected_version:
        raise BizError("兑换活动已更新，请刷新后重试", status_code=409)
    if campaign.status != status:
        campaign.status = status
        campaign.last_modified_by = actor_user_id
        campaign.version = int(campaign.version or 1) + 1
        db.commit()
        db.refresh(campaign)
    return campaign


def redeem_code(
    db: Session,
    *,
    user_id: int,
    code: str,
    platform: str,
) -> Coupon:
    digest = redemption_code_hash(code)
    _begin_sqlite_write(db)
    campaign = db.query(CouponCampaign).filter(
        CouponCampaign.code_hash == digest
    ).with_for_update().first()
    if campaign is None:
        raise BizError("兑换码无效", status_code=400)
    now = utc_now()
    state = effective_campaign_status(campaign, now)
    if state == "scheduled":
        raise BizError("兑换活动尚未开始", status_code=409)
    if state == "expired":
        raise BizError("兑换码已过期", status_code=409)
    if state == "exhausted":
        raise BizError("兑换码已领完", status_code=409)
    if state != "active":
        raise BizError("兑换码无效或已停止使用", status_code=409)
    existing = db.query(Coupon.id).filter(
        Coupon.user_id == user_id,
        Coupon.campaign_id == campaign.id,
    ).first()
    if existing:
        raise BizError("您已兑换过该优惠券", status_code=409)

    expires_at = min(
        campaign.expires_at,
        now + timedelta(days=max(int(campaign.coupon_ttl_days or 1), 1)),
    )
    coupon = Coupon(
        user_id=user_id,
        campaign_id=campaign.id,
        product_id=campaign.product_id,
        name=campaign.name,
        amount=campaign.amount,
        min_amount=campaign.min_amount,
        status="available",
        expires_at=expires_at,
        redeemed_at=now,
        created_platform=normalize_platform(platform),
        last_modified_platform=normalize_platform(platform),
    )
    campaign.redeemed_count = int(campaign.redeemed_count or 0) + 1
    campaign.version = int(campaign.version or 1) + 1
    db.add(coupon)
    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise BizError("您已兑换过该优惠券", status_code=409) from exc
    db.refresh(coupon)
    return coupon


def eligible_coupons(
    db: Session,
    *,
    user_id: int,
    amount: Decimal | None,
    product_id: int | None,
    purchase_type: str,
) -> list[Coupon]:
    if purchase_type != "usage":
        return []
    now = utc_now()
    query = db.query(Coupon).filter(
        Coupon.user_id == user_id,
        Coupon.status == "available",
        or_(Coupon.expires_at.is_(None), Coupon.expires_at >= now),
    )
    if product_id is not None:
        query = query.filter(or_(Coupon.product_id.is_(None), Coupon.product_id == product_id))
    else:
        query = query.filter(Coupon.product_id.is_(None))
    if amount is not None:
        query = query.filter(Coupon.min_amount <= funding_amount(amount))
    return query.order_by(Coupon.amount.desc(), Coupon.expires_at.asc()).all()


def claim_coupon_for_order(
    db: Session,
    *,
    coupon_id: int | None,
    user_id: int,
    product_id: int,
    purchase_type: str,
    gross_amount: Decimal,
) -> tuple[Coupon | None, Decimal]:
    if coupon_id is None:
        return None, funding_amount(0)
    if purchase_type != "usage":
        raise BizError("优惠券仅适用于使用型算力订单", status_code=409)
    coupon = db.query(Coupon).filter(
        Coupon.id == coupon_id,
        Coupon.user_id == user_id,
    ).with_for_update().first()
    if coupon is None:
        raise BizError("优惠券不存在", status_code=404)
    if effective_coupon_status(coupon) != "available" or coupon.used_order_id is not None:
        raise BizError("优惠券已使用或已过期", status_code=409)
    if coupon.product_id is not None and int(coupon.product_id) != int(product_id):
        raise BizError("该优惠券不适用于当前商品", status_code=409)
    gross = funding_amount(gross_amount)
    if gross < funding_amount(coupon.min_amount):
        raise BizError("订单金额未达到优惠券使用门槛", status_code=409)
    discount = min(funding_amount(coupon.amount), gross)
    if discount <= 0:
        raise BizError("优惠券面额无效", status_code=409)
    return coupon, discount


def apply_coupon_to_order(
    db: Session,
    *,
    coupon: Coupon,
    order: Order,
    wallet: Wallet,
    discount: Decimal,
    platform: str,
) -> None:
    value = funding_amount(discount)
    wallet.balance = funding_amount(wallet.balance) + value
    wallet.promotional_balance = funding_amount(wallet.promotional_balance) + value
    order.coupon_id = coupon.id
    order.coupon_discount = value
    coupon.status = "used"
    coupon.used_at = utc_now()
    coupon.used_order_id = order.id
    coupon.last_modified_platform = normalize_platform(platform)
    coupon.version = int(coupon.version or 1) + 1
    db.add(Ledger(
        user_id=order.user_id,
        wallet_id=wallet.id,
        type="coupon_credit",
        direction="in",
        amount=value,
        balance_after=funding_amount(wallet.balance),
        ref_order_id=order.id,
        event_key=f"coupon:{coupon.id}:order:{order.id}:apply",
        remark=f"优惠券抵扣 {coupon.name} / {order.order_no}",
    ))


def restore_coupon_from_order(
    db: Session,
    *,
    order: Order,
    wallet: Wallet,
    platform: str,
) -> None:
    if order.coupon_id is None or funding_amount(order.coupon_discount) <= 0:
        return
    coupon = db.query(Coupon).filter(Coupon.id == order.coupon_id).with_for_update().first()
    if coupon is None or coupon.used_order_id != order.id or coupon.status != "used":
        return
    value = funding_amount(order.coupon_discount)
    if (
        funding_amount(wallet.balance) < value
        or funding_amount(wallet.promotional_balance) < value
    ):
        raise BizError("优惠券退款资金状态异常，请联系平台服务人员核查", status_code=409)
    wallet.balance = funding_amount(wallet.balance) - value
    wallet.promotional_balance = funding_amount(wallet.promotional_balance) - value
    coupon.status = "expired" if coupon.expires_at and coupon.expires_at < utc_now() else "available"
    coupon.used_at = None
    coupon.used_order_id = None
    coupon.last_modified_platform = normalize_platform(platform)
    coupon.version = int(coupon.version or 1) + 1
    db.add(Ledger(
        user_id=order.user_id,
        wallet_id=wallet.id,
        type="coupon_restore",
        direction="out",
        amount=value,
        balance_after=funding_amount(wallet.balance),
        ref_order_id=order.id,
        event_key=f"coupon:{coupon.id}:order:{order.id}:restore",
        remark=f"订单取消，恢复优惠券 {coupon.name} / {order.order_no}",
    ))
