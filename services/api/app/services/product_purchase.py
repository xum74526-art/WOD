from __future__ import annotations

from collections.abc import Mapping

from sqlalchemy.orm import Session

from app.core.config import settings
from app.models.supplier import Supplier
from app.models.user import User
from app.services.market_freshness import product_market_source


UNVERIFIED_SUPPLIER_REASON = "该资源尚未关联入驻资料已审核的KAI星算商家，暂不可下单"
UNAVAILABLE_LISTING_REASON = "该资源已下架或暂不可购买"
RETIRED_MARKET_SOURCE_REASON = "该行情来源已停用，仅保留历史记录"
PLATFORM_FULFILLMENT_UNAVAILABLE_REASON = "平台履约暂未配置，当前不可下单"


def configured_platform_fulfiller_ids(db: Session) -> set[int]:
    configured: set[int] = set()
    for value in str(settings.PLATFORM_FULFILLMENT_USER_IDS or "").split(","):
        try:
            configured.add(int(value.strip()))
        except (TypeError, ValueError):
            continue
    configured_ids = {
        int(user_id)
        for (user_id,) in db.query(User.id).filter(
            User.id.in_(configured or {-1}),
            User.account_status == "active",
        ).all()
    }
    administrator_ids = {
        int(user_id)
        for (user_id,) in db.query(User.id).filter(
            User.role == "admin",
            User.account_status == "active",
        ).all()
    }
    return configured_ids | administrator_ids


def product_purchase_availability(
    product,
    db: Session,
    *,
    platform_fulfiller_ids: set[int] | None = None,
    suppliers: Mapping[int, Supplier] | None = None,
) -> tuple[bool, str | None]:
    """Return whether ZTW can actually fulfil this offer.

    Provider-backed cards may enter the manual-fulfilment order workflow while their
    quote is live. They still require manual SSH fulfilment and never create an
    asset at checkout. ZTW-branded listings additionally require an approved supplier.
    """
    if product.status != "on":
        return False, UNAVAILABLE_LISTING_REASON
    source = product_market_source(product)
    if source == "kai":
        fulfiller_ids = (
            configured_platform_fulfiller_ids(db)
            if platform_fulfiller_ids is None
            else platform_fulfiller_ids
        )
        if not fulfiller_ids:
            return False, PLATFORM_FULFILLMENT_UNAVAILABLE_REASON
        return True, None
    if source != "wod":
        return False, RETIRED_MARKET_SOURCE_REASON
    if not product.supplier_id:
        return False, UNVERIFIED_SUPPLIER_REASON
    supplier = (
        suppliers.get(int(product.supplier_id))
        if suppliers is not None
        else db.query(Supplier).filter(Supplier.id == product.supplier_id).first()
    )
    if not supplier or supplier.status != "approved":
        return False, UNVERIFIED_SUPPLIER_REASON
    if suppliers is None:
        owner_active = db.query(User.id).filter(
            User.id == supplier.user_id,
            User.account_status == "active",
        ).first()
        if owner_active is None:
            return False, UNVERIFIED_SUPPLIER_REASON
    return True, None
