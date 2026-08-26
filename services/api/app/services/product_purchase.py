from __future__ import annotations

from sqlalchemy.orm import Session

from app.core.config import settings
from app.models.supplier import Supplier
from app.models.user import User
from app.services.market_freshness import product_market_source


UNVERIFIED_SUPPLIER_REASON = "该资源尚未关联入驻资料已审核的 WOD 商家，暂不可下单"
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
    if not configured:
        return set()
    return {
        int(user_id)
        for (user_id,) in db.query(User.id).filter(User.id.in_(configured)).all()
    }


def product_purchase_availability(product, db: Session) -> tuple[bool, str | None]:
    """Return whether WOD can actually fulfil this offer.

    Provider-backed cards may enter the manual-fulfilment order workflow while their
    quote is live. They still require manual SSH fulfilment and never create an
    asset at checkout. WOD listings additionally require an approved supplier.
    """
    if product.status != "on":
        return False, UNAVAILABLE_LISTING_REASON
    source = product_market_source(product)
    if source == "kai":
        if not configured_platform_fulfiller_ids(db):
            return False, PLATFORM_FULFILLMENT_UNAVAILABLE_REASON
        return True, None
    if source != "wod":
        return False, RETIRED_MARKET_SOURCE_REASON
    if not product.supplier_id:
        return False, UNVERIFIED_SUPPLIER_REASON
    supplier = db.query(Supplier).filter(Supplier.id == product.supplier_id).first()
    if not supplier or supplier.status != "approved":
        return False, UNVERIFIED_SUPPLIER_REASON
    return True, None
