from datetime import datetime, timedelta

from fastapi import APIRouter, Depends, Query
from sqlalchemy import and_, or_
from sqlalchemy.orm import Session

from app.core.config import settings
from app.db.session import get_db
from app.models.market_price import MarketSourceStatus
from app.models.product import Product
from app.schemas.product import ProductOut
from app.services.purchase_cycles import available_purchase_cycles
from app.services.market_freshness import CURRENT_SOURCE_STATES, product_market_source, product_market_state, source_state
from app.services.market_sync import utcnow
from app.services.product_purchase import product_purchase_availability
from app.services.region_mapper import REGIONS
from app.utils.response import BizError, success

router = APIRouter(prefix="/api/products", tags=["product"])

CATEGORY_MAP = {
    "h_series": ["H100", "H200", "H800", "H20"],
    "a_series": ["A100", "A800"],
    "consumer": ["RTX4090", "RTX4090D", "RTX4080", "RTX3090", "RTX3080", "RTX3080Ti", "RTX5090", "RTX2080Ti", "RTX3070", "RTX3060", "RTX2060", "RTX2070"],
    "professional": ["RTXPRO6000", "A6000", "A40", "A30", "A10", "A4000", "A5000", "L40S", "L40", "T4", "V100"],
    "domestic": ["MTTS4000"],
    "vgpu": ["vGPU32", "vGPU48"],
}


def _market_source_states(db: Session) -> dict[str, str]:
    now = utcnow()
    return {
        row.source: source_state(row, now)
        for row in db.query(MarketSourceStatus).all()
        if row.enabled
    }


def _current_product_query(db: Session, source_states: dict[str, str] | None = None):
    states = source_states if source_states is not None else _market_source_states(db)
    cutoff = utcnow() - timedelta(seconds=max(settings.PRODUCT_OFFER_MAX_AGE_SECONDS, 60))
    source_filters = [Product.source_price.is_(None)]
    # A provider's last successful snapshot remains truthful during the short
    # ``delayed`` grace window. Keep those reference cards visible instead of
    # collapsing the catalogue to WOD-only listings; _product_out still marks
    # them delayed, zeroes stock and disables purchase. Stale/unavailable
    # sources remain excluded.
    if states.get("autodl") in CURRENT_SOURCE_STATES:
        source_filters.append(and_(
            Product.source_price.isnot(None),
            Product.source_currency == "CNY",
            Product.price_updated_at >= cutoff,
        ))
    if states.get("vast") in CURRENT_SOURCE_STATES:
        source_filters.append(and_(
            Product.source_price.isnot(None),
            Product.source_currency == "USD",
            Product.price_updated_at >= cutoff,
        ))
    return db.query(Product).filter(Product.status == "on", or_(*source_filters))


def _product_out(p: Product, db: Session = None, source_states: dict[str, str] | None = None) -> dict:
    out = ProductOut.model_validate(p).model_dump()
    # A product price is a rental quote, not evidence of compute revenue.
    # Keep revenue blank until a verified metering/settlement source is wired.
    out["daily_revenue"] = None
    out["revenue_estimate_available"] = False
    out["cycle"] = available_purchase_cycles(p.cycle)
    source = product_market_source(p)
    states = source_states if source_states is not None else (_market_source_states(db) if db else {})
    market_state = product_market_state(p, states, utcnow(), settings.PRODUCT_OFFER_MAX_AGE_SECONDS)
    reported_stock = max(int(p.stock or 0), 0)
    out["stock"] = reported_stock if market_state == "live" else 0
    out["reported_stock"] = reported_stock
    out["market_source"] = source
    out["market_source_status"] = market_state
    out["is_market_current"] = market_state == "live"
    # Legacy SQLite migrations stored ``reliability`` as TEXT and some rows use
    # placeholders such as "-".  Never let a display-only field break the
    # complete product catalogue.
    try:
        reliability = float(p.reliability or 0)
    except (TypeError, ValueError):
        reliability = 0
    out["stability"] = round(reliability, 1) if reliability > 0 else None
    out["tags"] = []
    out["supplier_id"] = p.supplier_id
    purchasable, unavailable_reason = product_purchase_availability(p, db) if db else (False, None)
    out["purchasable"] = purchasable and market_state == "live" and reported_stock > 0
    out["purchase_unavailable_reason"] = (
        unavailable_reason
        if not purchasable
        else ("当前无可售库存" if reported_stock <= 0 else ("报价已过期或来源暂不可用" if market_state != "live" else None))
    )
    # 关联供应商名
    if p.supplier_id and db:
        from app.models.supplier import Supplier
        s = db.query(Supplier).filter(Supplier.id == p.supplier_id).first()
        out["supplier_name"] = s.company_name if s else None
    return out


@router.get("")
def list_products(
    keyword: str | None = None,
    memory: str | None = None,
    region: str | None = None,
    category: str | None = None,
    sort: str = "default",
    min_price: float | None = None,
    max_price: float | None = None,
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    db: Session = Depends(get_db),
):
    source_states = _market_source_states(db)
    q = _current_product_query(db, source_states)
    if keyword:
        q = q.filter(Product.name.contains(keyword) | Product.gpu_model.contains(keyword))
    if memory:
        q = q.filter(Product.memory.contains(memory))
    if region:
        q = q.filter(Product.region_code == region)
    if category and category in CATEGORY_MAP:
        q = q.filter(Product.gpu_model.in_(CATEGORY_MAP[category]))
    if min_price is not None:
        q = q.filter(Product.price >= min_price)
    if max_price is not None:
        q = q.filter(Product.price <= max_price)
    if sort == "price_asc":
        q = q.order_by(Product.price.asc())
    elif sort == "price_desc":
        q = q.order_by(Product.price.desc())
    else:
        q = q.order_by(Product.price_updated_at.desc())
    total = q.count()
    items = q.offset((page - 1) * page_size).limit(page_size).all()
    return success({"items": [_product_out(p, db, source_states) for p in items], "total": total, "page": page, "page_size": page_size})


@router.get("/filters")
def filters(db: Session = Depends(get_db)):
    regions = [{"code": r["code"], "name": r["name"]} for r in REGIONS]
    return success({"regions": regions})


@router.get("/quote/overview")
def quote_overview(db: Session = Depends(get_db)):
    """Legacy product overview using current cards only.

    The old ``PriceHistory`` table has no source, memory or billing identity,
    so its cross-product percentage cannot truthfully be called a 24-hour
    change.  Keep the compatibility endpoint, but return an explicit null
    change and direct clients to ``/api/market/ranking`` for verified history.
    """
    current_products = _current_product_query(db).all()
    grouped = {}
    for product in current_products:
        grouped.setdefault((product.gpu_model, product.memory), []).append(product)
    ranking = []
    for (gpu_model, memory), products in grouped.items():
        prices = [float(p.price) for p in products]
        min_price = min(prices)
        avg_price = round(sum(prices) / len(prices), 4)
        total_stock = sum((int(p.stock) if p.stock is not None else 0) for p in products)
        ranking.append({
            "gpu_model": gpu_model,
            "gpu_variant": memory,
            "name": products[0].name,
            "min_price": min_price,
            "avg_price": avg_price,
            "total_stock": total_stock,
            "supplier_count": len(set(p.supplier_id for p in products if p.supplier_id)),
            "change": None,
            "change_status": "use_market_ranking",
        })
    ranking.sort(key=lambda x: x["min_price"])
    return success({"ranking": ranking[:20]})


@router.get("/quote/regional")
def quote_regional(db: Session = Depends(get_db)):
    """区域价差：按region_name聚合"""
    from collections import defaultdict
    products = _current_product_query(db).all()
    by_region = defaultdict(list)
    for p in products:
        rn = p.region_name or "未知"
        by_region[rn].append(float(p.price))
    result = []
    for region, prices in by_region.items():
        result.append({
            "region": region,
            "avg_price": round(sum(prices) / len(prices), 4),
            "min_price": min(prices),
            "count": len(prices),
        })
    result.sort(key=lambda x: x["avg_price"])
    return success({"regions": result})


@router.get("/{pid}")
def get_product(pid: int, db: Session = Depends(get_db)):
    p = db.query(Product).filter(Product.id == pid).first()
    if not p:
        raise BizError("商品不存在", status_code=404)
    return success(_product_out(p, db))


@router.get("/{pid}/price-trend")
def price_trend(pid: int, db: Session = Depends(get_db)):
    p = db.query(Product).filter(Product.id == pid).first()
    if not p:
        raise BizError("商品不存在", status_code=404)
    from app.models.market_price import MarketPriceSnapshot
    from app.services.gpu_catalog import canonicalize_gpu, gpu_variant_aliases, normalize_gpu_variant

    model = canonicalize_gpu(p.gpu_model) or canonicalize_gpu(p.name)
    variant = normalize_gpu_variant(model, p.memory)
    variant_filters = gpu_variant_aliases(model, variant)
    if not model:
        return success([])
    source = product_market_source(p)
    billing_mode = "wod_listing" if source == "wod" else "ondemand"
    rows = db.query(MarketPriceSnapshot).filter(
        MarketPriceSnapshot.gpu_model == model,
        MarketPriceSnapshot.gpu_variant.in_(variant_filters),
        MarketPriceSnapshot.source == source,
        MarketPriceSnapshot.billing_mode == billing_mode,
        MarketPriceSnapshot.observed_at >= utcnow() - timedelta(days=30),
        MarketPriceSnapshot.median_price_cny.isnot(None),
    ).order_by(MarketPriceSnapshot.observed_at.asc()).all()
    return success([{
        "date": row.observed_at.strftime("%m-%d %H:%M"),
        "price": float(row.median_price_cny),
        "source": row.source,
        "billing_mode": row.billing_mode,
        "observed_at": row.observed_at.isoformat(timespec="seconds") + "Z",
    } for row in rows])
