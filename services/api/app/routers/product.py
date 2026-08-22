from collections import defaultdict
from datetime import datetime, timedelta
from decimal import Decimal

from fastapi import APIRouter, Depends, Query
from sqlalchemy import and_, or_
from sqlalchemy.orm import Session

from app.core.config import settings
from app.db.session import get_db
from app.models.market_price import MarketSourceStatus
from app.models.product import Product
from app.schemas.product import ProductOut
from app.services.purchase_cycles import PURCHASE_HOUR_OPTIONS, available_purchase_cycles
from app.services.market_freshness import CURRENT_SOURCE_STATES, product_market_source, product_market_state, source_state
from app.services.market_sync import utcnow
from app.services.product_purchase import product_purchase_availability
from app.services.gpu_catalog import canonicalize_gpu, normalize_gpu_variant
from app.services.region_mapper import REGIONS, map_region
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

KAI_PUBLIC_DESCRIPTION = (
    "KAI Pricing 当前卡时报价；可购数量为平台人工履约额度，"
    "上游数量仅表示单次最大可配置量，不是实时库存"
)


def _market_source_states(db: Session) -> dict[str, str]:
    now = utcnow()
    return {
        row.source: source_state(row, now)
        for row in db.query(MarketSourceStatus).all()
        if row.enabled and row.source == "kai"
    }


def _current_product_query(db: Session, source_states: dict[str, str] | None = None):
    states = source_states if source_states is not None else _market_source_states(db)
    cutoff = utcnow() - timedelta(seconds=max(settings.PRODUCT_OFFER_MAX_AGE_SECONDS, 60))
    # First-party merchant rows remain in the catalogue. KAI is the only
    # third-party source allowed to contribute current product cards.
    legacy_untyped = or_(Product.market_source.is_(None), Product.market_source == "")
    source_filters = [or_(
        Product.market_source == "wod",
        and_(legacy_untyped, Product.source_price.is_(None)),
    )]
    if states.get("kai") in CURRENT_SOURCE_STATES:
        source_filters.append(and_(
                Product.market_source == "kai",
                Product.source_price.isnot(None),
                Product.price_updated_at.isnot(None),
                Product.price_updated_at >= cutoff,
        ))
    return db.query(Product).filter(Product.status == "on", or_(*source_filters))


def _product_out(p: Product, db: Session = None, source_states: dict[str, str] | None = None) -> dict:
    out = ProductOut.model_validate(p).model_dump()
    # A product price is a rental quote, not evidence of compute revenue.
    # Keep revenue blank until a verified metering/settlement source is wired.
    out["daily_revenue"] = None
    out["revenue_estimate_available"] = False
    source = product_market_source(p)
    if source == "kai":
        # Some deployed databases still contain the former rollout wording.
        # The API is the compatibility boundary: never expose stale copy even
        # before the next catalogue synchronization updates stored rows.
        out["desc"] = KAI_PUBLIC_DESCRIPTION
        cny_price = Decimal(str(p.price or 0))
        rate = Decimal(str(settings.CARD_HOUR_RMB_RATE or 0))
        out["cycle"] = []
        out["billing_unit"] = "GPU_HOUR"
        out["price_currency"] = "CNY"
        out["price_cny_per_gpu_hour"] = float(cny_price)
        out["price_card_hours_per_gpu_hour"] = (
            float((cny_price / rate).quantize(Decimal("0.000001"))) if rate > 0 else None
        )
        out["wallet_charge_unit"] = "CARD_HOUR"
        out["purchase_unit"] = "hour"
        out["purchase_hour_options"] = list(PURCHASE_HOUR_OPTIONS)
    else:
        out["cycle"] = available_purchase_cycles(p.cycle)
        out["billing_unit"] = "GPU_HOUR"
        out["price_currency"] = "CARD_HOUR"
        out["price_cny_per_gpu_hour"] = float(Decimal(str(p.price or 0)) * Decimal(str(settings.CARD_HOUR_RMB_RATE)))
        out["price_card_hours_per_gpu_hour"] = float(p.price or 0)
        out["wallet_charge_unit"] = "CARD_HOUR"
        out["purchase_unit"] = "day"
        out["purchase_hour_options"] = []
    states = source_states if source_states is not None else (_market_source_states(db) if db else {})
    market_state = product_market_state(p, states, utcnow(), settings.PRODUCT_OFFER_MAX_AGE_SECONDS)
    reported_stock = max(int(p.stock or 0), 0)
    if source == "kai" and p.platform_stock_cap is not None:
        reported_stock = min(reported_stock, max(int(p.platform_stock_cap), 0))
    out["stock"] = reported_stock if market_state == "live" else 0
    out["reported_stock"] = None if source == "kai" else reported_stock
    out["market_source"] = source
    out["stock_semantics"] = (
        "platform_manual_fulfillment_allocation" if source == "kai" else p.stock_semantics
    )
    out["max_configurable_quantity"] = (
        max(int(p.source_max_configurable_quantity or 0), 0) or None
        if source == "kai"
        else None
    )
    out["source_max_configurable_quantity"] = (
        max(int(p.source_max_configurable_quantity or 0), 0) or None
        if source == "kai" else None
    )
    out["platform_stock_cap"] = (
        max(int(p.platform_stock_cap or 0), 0) if source == "kai" else None
    )
    out["platform_stock_remaining"] = reported_stock if source == "kai" else None
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
    effective_purchase_capacity = reported_stock
    if source == "kai":
        effective_purchase_capacity = min(
            effective_purchase_capacity,
            max(int(p.source_max_configurable_quantity or 0), 0),
        )
    out["purchasable"] = purchasable and market_state == "live" and effective_purchase_capacity > 0
    out["purchase_unavailable_reason"] = (
        unavailable_reason
        if not purchasable
        else ("当前无可售额度" if effective_purchase_capacity <= 0 else ("报价已过期或来源暂不可用" if market_state != "live" else None))
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
    """KAI-only current cross-section; observations are not inventory."""
    current_products = _current_product_query(db).filter(Product.market_source == "kai").all()
    grouped = {}
    for product in current_products:
        model = canonicalize_gpu(product.gpu_model) or product.gpu_model
        variant = normalize_gpu_variant(model, product.memory)
        grouped.setdefault((model, variant), []).append(product)
    ranking = []
    for (gpu_model, memory), products in grouped.items():
        prices = sorted(Decimal(str(p.price)) for p in products if Decimal(str(p.price or 0)) > 0)
        if not prices:
            continue
        midpoint = len(prices) // 2
        median = (
            (prices[midpoint - 1] + prices[midpoint]) / Decimal("2")
            if len(prices) % 2 == 0 else prices[midpoint]
        )
        ranking.append({
            "gpu_model": gpu_model,
            "gpu_variant": memory,
            "name": products[0].name,
            "median_price_cny": float(median),
            "min_price_cny": float(min(prices)),
            "max_price_cny": float(max(prices)),
            "quote_sample_count": len(prices),
            "region_count": len({map_region(p.city, p.country_code)[0] for p in products}),
            "change": None,
            "change_status": "use_market_ranking",
            "source": "kai",
            "billing_unit": "GPU_HOUR",
            "sample_semantics": "current_quote_observations_not_inventory",
        })
    ranking.sort(key=lambda item: (item["median_price_cny"], item["gpu_model"], item["gpu_variant"]))
    return success({
        "ranking": ranking[:20],
        "source": "kai",
        "billing_unit": "GPU_HOUR",
        "sample_semantics": "current_quote_observations_not_inventory",
    })


def _decimal_percentile(values: list[Decimal], ratio: Decimal) -> Decimal:
    ordered = sorted(values)
    if not ordered:
        return Decimal("0")
    if len(ordered) == 1:
        return ordered[0]
    position = Decimal(len(ordered) - 1) * ratio
    lower = int(position)
    upper = min(lower + 1, len(ordered) - 1)
    fraction = position - Decimal(lower)
    return ordered[lower] + (ordered[upper] - ordered[lower]) * fraction


@router.get("/quote/regional")
def quote_regional(
    model: str | None = None,
    variant: str | None = None,
    db: Session = Depends(get_db),
):
    """Compare one exact KAI model/VRAM identity across published regions.

    Omitting ``model`` selects the identity observed in the most distinct
    normalized regions, then the largest quote count, then lexical identity.
    This deterministic fallback never averages prices from different GPUs.
    """
    if variant and not model:
        raise BizError("指定显存时必须同时指定 GPU 型号", status_code=400)
    source_states = _market_source_states(db)
    products = _current_product_query(db, source_states).filter(Product.market_source == "kai").all()
    identities: dict[tuple[str, str], list[Product]] = defaultdict(list)
    for product in products:
        canonical_model = canonicalize_gpu(product.gpu_model) or product.gpu_model
        canonical_variant = normalize_gpu_variant(canonical_model, product.memory)
        identities[(canonical_model, canonical_variant)].append(product)

    requested_model = canonicalize_gpu(model) or str(model or "").strip()
    requested_variant = normalize_gpu_variant(requested_model, variant) if requested_model and variant else ""
    candidates = [
        (identity, rows) for identity, rows in identities.items()
        if (not requested_model or identity[0] == requested_model)
        and (not requested_variant or identity[1] == requested_variant)
    ]
    candidates.sort(key=lambda item: (
        -len({map_region(row.city, row.country_code)[0] for row in item[1]}),
        -len(item[1]),
        item[0][0],
        item[0][1],
    ))
    if not candidates:
        return success({
            "gpu_model": requested_model or None,
            "gpu_variant": requested_variant or None,
            "source": "kai",
            "billing_unit": "GPU_HOUR",
            "region_count": 0,
            "regions": [],
            "market_status": source_states.get("kai", "unavailable"),
            "sample_semantics": "current_quote_observations_not_inventory",
        })

    (selected_model, selected_variant), selected_products = candidates[0]
    by_region: dict[tuple[str, str], list[Product]] = defaultdict(list)
    for product in selected_products:
        by_region[map_region(product.city, product.country_code)].append(product)

    result = []
    for (region_code, region_name), rows in by_region.items():
        values = sorted(Decimal(str(row.price)) for row in rows if Decimal(str(row.price or 0)) > 0)
        if not values:
            continue
        median = _decimal_percentile(values, Decimal("0.5"))
        observed_at = max((row.price_updated_at for row in rows if row.price_updated_at), default=None)
        result.append({
            "region_code": region_code,
            "region": region_name,
            "median_price_cny": float(median),
            "min_price_cny": float(min(values)),
            "max_price_cny": float(max(values)),
            "p25_price_cny": float(_decimal_percentile(values, Decimal("0.25"))),
            "p75_price_cny": float(_decimal_percentile(values, Decimal("0.75"))),
            "quote_sample_count": len(values),
            "location_count": len({str(row.city or "").strip() for row in rows if str(row.city or "").strip()}),
            "observed_at": observed_at.isoformat(timespec="seconds") + "Z" if observed_at else None,
        })
    result.sort(key=lambda item: (item["median_price_cny"], item["region"], item["region_code"]))
    lowest = result[0]["median_price_cny"] if result else None
    for item in result:
        item["relative_to_lowest_pct"] = (
            round((item["median_price_cny"] / lowest - 1) * 100, 2) if lowest and lowest > 0 else None
        )
        item["is_lowest"] = item["median_price_cny"] == lowest if lowest is not None else False
    return success({
        "gpu_model": selected_model,
        "gpu_variant": selected_variant,
        "source": "kai",
        "billing_unit": "GPU_HOUR",
        "region_count": len(result),
        "regions": result,
        "market_status": source_states.get("kai", "unavailable"),
        "selection": "requested_identity" if requested_model else "most_region_coverage_then_quote_count",
        "sample_semantics": "current_quote_observations_not_inventory",
    })


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
