from __future__ import annotations

from sqlalchemy.orm import Session

from app.models.supplier import Supplier
from app.services.market_freshness import product_market_source


KAI_ASSURANCE_LABEL = "KAI 自营 · 平台人工交付"
KAI_ASSURANCE_DESCRIPTION = (
    "商品由 KAI 发布并由平台安排人工交付；买家确认后订单完成，"
    "交付异常可在验收期内发起争议。"
)
MERCHANT_ASSURANCE_LABEL = "商家入驻资料已审核 · 商家人工交付"
MERCHANT_ASSURANCE_DESCRIPTION = (
    "平台已完成商家入驻资料审核；商品配置与库存由商家自行申报，"
    "买家确认交付后资金才向商家结算，交付异常可在验收期内发起争议。"
)
UNVERIFIED_MERCHANT_ASSURANCE_LABEL = "商家状态待核验"
UNVERIFIED_MERCHANT_ASSURANCE_DESCRIPTION = (
    "该商品尚未关联已审核商家，当前不可下单。"
)


def product_provider_info(product, db: Session | None = None) -> dict:
    """Return public seller and fulfilment facts for a product.

    Merchant approval records a review of onboarding materials only.  It must
    never be presented as identity certification or as a platform audit of the
    merchant's hardware, configuration or live inventory, all of which remain
    merchant-declared until delivery.
    """

    source = product_market_source(product)
    if source == "kai":
        return {
            "supplier_id": None,
            "supplier_name": None,
            "supplier_rating": None,
            "supplier_order_count": None,
            "seller_type": "kai_self_operated",
            "seller_name": "KAI 自营",
            "fulfillment_mode": "platform_manual",
            "resource_claim_source": "kai_published",
            "assurance_label": KAI_ASSURANCE_LABEL,
            "assurance_description": KAI_ASSURANCE_DESCRIPTION,
        }

    supplier = None
    supplier_id = getattr(product, "supplier_id", None)
    if source == "wod" and supplier_id and db is not None:
        supplier = db.query(Supplier).filter(Supplier.id == supplier_id).first()
    approved = bool(supplier and supplier.status == "approved")
    supplier_name = supplier.company_name if supplier else None
    return {
        "supplier_id": supplier_id,
        "supplier_name": supplier_name,
        "supplier_rating": float(supplier.rating) if approved else None,
        "supplier_order_count": int(supplier.order_count or 0) if approved else None,
        "seller_type": "merchant" if source == "wod" else "unknown",
        "seller_name": supplier_name,
        "fulfillment_mode": "merchant_manual" if source == "wod" else None,
        "resource_claim_source": "merchant_declared" if source == "wod" else None,
        "assurance_label": (
            MERCHANT_ASSURANCE_LABEL if approved else UNVERIFIED_MERCHANT_ASSURANCE_LABEL
        ),
        "assurance_description": (
            MERCHANT_ASSURANCE_DESCRIPTION
            if approved
            else UNVERIFIED_MERCHANT_ASSURANCE_DESCRIPTION
        ),
    }
