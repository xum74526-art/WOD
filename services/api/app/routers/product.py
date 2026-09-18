from collections import defaultdict
from datetime import datetime, timedelta
from decimal import Decimal
from typing import Literal

from fastapi import APIRouter, Depends, Query
from sqlalchemy import and_, false, or_
from sqlalchemy.orm import Session

from app.core.config import settings
from app.db.session import get_db
from app.models.market_price import MarketSourceStatus
from app.models.product import Product
from app.models.supplier import Supplier
from app.schemas.product import ProductOut
from app.services.purchase_cycles import (
    MAX_PURCHASE_HOURS,
    MIN_PURCHASE_HOURS,
    PURCHASE_HOUR_OPTIONS,
    available_purchase_cycles,
)
from app.services.market_freshness import CURRENT_SOURCE_STATES, product_market_source, product_market_state, source_state
from app.services.market_sync import utcnow
from app.services.offer_sync import KAI_PRODUCT_DESCRIPTION
from app.services.product_purchase import configured_platform_fulfiller_ids, product_purchase_availability
from app.services.product_provider import product_provider_info
from app.services.trade_mode import (
    INQUIRY_ONLY_MESSAGE,
    commerce_mode,
    direct_trade_enabled,
    matchmaking_enabled,
)
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

def _market_source_states(db: Session) -> dict[str, str]:
    now = utcnow()
    return {
        row.source: source_state(row, now)
        for row in db.query(MarketSourceStatus).all()
        if row.enabled and row.source == "kai"
    }


def _legacy_wod_product_filter():
    """Match merchant rows created before ``market_source`` was persisted."""

    return and_(
        or_(Product.market_source.is_(None), Product.market_source == ""),
        Product.source_price.is_(None),
    )


def _current_product_query(
    db: Session,
    source_states: dict[str, str] | None = None,
    *,
    include_merchants: bool = True,
):
    states = source_states if source_states is not None else _market_source_states(db)
    cutoff = utcnow() - timedelta(seconds=max(settings.PRODUCT_OFFER_MAX_AGE_SECONDS, 60))
    # Only approved merchant listings and current KAI self-operated cards are
    # eligible for the public catalogue. Retired sources remain audit-only.
    approved_supplier_ids = db.query(Supplier.id).filter(Supplier.status == "approved")
    source_filters = []
    if include_merchants and settings.THIRD_PARTY_MERCHANT_PUBLIC_CATALOG_ENABLED is True:
        source_filters.append(and_(
            or_(
                Product.market_source == "wod",
                _legacy_wod_product_filter(),
            ),
            Product.supplier_id.in_(approved_supplier_ids),
        ))
    if states.get("kai") in CURRENT_SOURCE_STATES:
        source_filters.append(and_(
                Product.market_source == "kai",
                Product.source_price.isnot(None),
                Product.price_updated_at.isnot(None),
                Product.price_updated_at >= cutoff,
        ))
    return db.query(Product).filter(
        Product.status == "on",
        or_(*source_filters) if source_filters else false(),
    )


def _product_out(
    p: Product,
    db: Session = None,
    source_states: dict[str, str] | None = None,
    *,
    platform_fulfiller_ids: set[int] | None = None,
    suppliers: dict[int, Supplier] | None = None,
) -> dict:
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
        out["desc"] = KAI_PRODUCT_DESCRIPTION
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
        out["min_purchase_hours"] = MIN_PURCHASE_HOURS
        out["max_purchase_hours"] = MAX_PURCHASE_HOURS
    elif source == "wod":
        out["cycle"] = []
        out["billing_unit"] = "GPU_HOUR"
        out["price_currency"] = "CARD_HOUR"
        out["price_cny_per_gpu_hour"] = float(Decimal(str(p.price or 0)) * Decimal(str(settings.CARD_HOUR_RMB_RATE)))
        out["price_card_hours_per_gpu_hour"] = float(p.price or 0)
        out["wallet_charge_unit"] = "CARD_HOUR"
        out["purchase_unit"] = "hour"
        out["purchase_hour_options"] = list(PURCHASE_HOUR_OPTIONS)
        out["min_purchase_hours"] = MIN_PURCHASE_HOURS
        out["max_purchase_hours"] = MAX_PURCHASE_HOURS
    else:
        out["cycle"] = available_purchase_cycles(p.cycle)
        out["billing_unit"] = "GPU_HOUR"
        out["price_currency"] = "CARD_HOUR"
        out["price_cny_per_gpu_hour"] = float(Decimal(str(p.price or 0)) * Decimal(str(settings.CARD_HOUR_RMB_RATE)))
        out["price_card_hours_per_gpu_hour"] = float(p.price or 0)
        out["wallet_charge_unit"] = "CARD_HOUR"
        out["purchase_unit"] = "day"
        out["purchase_hour_options"] = []
        out["min_purchase_hours"] = None
        out["max_purchase_hours"] = None
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
    out.update(product_provider_info(p, db, suppliers))
    interaction_mode = commerce_mode()
    inquiry_available = matchmaking_enabled()
    out["interaction_mode"] = interaction_mode
    out["inquiry_available"] = inquiry_available
    purchasable, unavailable_reason = (
        product_purchase_availability(
            p,
            db,
            platform_fulfiller_ids=platform_fulfiller_ids,
            suppliers=suppliers,
        )
        if db else (False, None)
    )
    effective_purchase_capacity = reported_stock
    if source == "kai":
        effective_purchase_capacity = min(
            effective_purchase_capacity,
            max(int(p.source_max_configurable_quantity or 0), 0),
        )
    out["purchasable"] = bool(
        direct_trade_enabled()
        and purchasable
        and market_state == "live"
        and effective_purchase_capacity > 0
    )
    if not direct_trade_enabled():
        out["purchase_unavailable_reason"] = (
            INQUIRY_ONLY_MESSAGE if inquiry_available else "交易服务暂未开放"
        )
    else:
        out["purchase_unavailable_reason"] = (
            unavailable_reason
            if not purchasable
            else ("当前无可售额度" if effective_purchase_capacity <= 0 else ("报价已过期或来源暂不可用" if market_state != "live" else None))
        )
    return out


def _product_serialization_context(
    products: list[Product],
    db: Session,
) -> tuple[set[int], dict[int, Supplier]]:
    """Resolve list-wide purchase and provider facts with bounded queries."""

    sources = {product_market_source(product) for product in products}
    platform_fulfiller_ids = (
        configured_platform_fulfiller_ids(db) if "kai" in sources else set()
    )
    supplier_ids = {
        int(product.supplier_id)
        for product in products
        if product_market_source(product) == "wod" and product.supplier_id
    }
    suppliers = (
        {
            int(supplier.id): supplier
            for supplier in db.query(Supplier).filter(Supplier.id.in_(supplier_ids)).all()
        }
        if supplier_ids else {}
    )
    return platform_fulfiller_ids, suppliers


def _representative_products(
    products: list[Product],
    db: Session,
    source_states: dict[str, str],
) -> list[dict]:
    """Return one purchasable, lowest-price card per exact GPU/VRAM identity."""
    platform_fulfiller_ids, suppliers = _product_serialization_context(products, db)
    representatives: dict[str, dict] = {}
    for product in products:
        item = _product_out(
            product,
            db,
            source_states,
            platform_fulfiller_ids=platform_fulfiller_ids,
            suppliers=suppliers,
        )
        # KAI is a quote catalogue, so one lowest-price representative per
        # exact GPU/VRAM identity is useful.  Every merchant listing is an
        # independent seller offer and must remain visible even when hardware
        # specifications match another merchant's product.
        identity = (
            f"kai|{str(item.get('gpu_model') or '').strip().casefold()}|"
            f"{str(item.get('memory') or '').strip().casefold()}"
            if item.get("market_source") == "kai"
            else f"product|{item.get('id')}"
        )
        current = representatives.get(identity)
        price = Decimal(str(item.get("price_card_hours_per_gpu_hour") or item.get("price") or 0))
        current_price = (
            Decimal(str(current.get("price_card_hours_per_gpu_hour") or current.get("price") or 0))
            if current else None
        )
        if (
            current is None
            or (bool(item.get("purchasable")) and not bool(current.get("purchasable")))
            or (
                bool(item.get("purchasable")) == bool(current.get("purchasable"))
                and current_price is not None
                and price < current_price
            )
        ):
            representatives[identity] = item
    return list(representatives.values())


@router.get("")
def list_products(
    keyword: str | None = None,
    memory: str | None = None,
    region: str | None = None,
    category: str | None = None,
    sort: str = "default",
    min_price: float | None = None,
    max_price: float | None = None,
    market_source: Literal["kai", "wod"] | None = Query(default=None),
    representative: bool = Query(default=False),
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
    if market_source == "wod":
        # Keep the explicit source filter compatible with pre-migration
        # merchant rows admitted by ``_current_product_query``.
        q = q.filter(or_(
            Product.market_source == "wod",
            _legacy_wod_product_filter(),
        ))
    elif market_source:
        q = q.filter(Product.market_source == market_source)
    if sort == "price_asc":
        q = q.order_by(Product.price.asc())
    elif sort == "price_desc":
        q = q.order_by(Product.price.desc())
    else:
        q = q.order_by(Product.price_updated_at.desc())
    if representative:
        items = _representative_products(q.all(), db, source_states)
        if sort == "price_asc":
            items.sort(key=lambda item: Decimal(str(item.get("price_card_hours_per_gpu_hour") or item.get("price") or 0)))
        elif sort == "price_desc":
            items.sort(
                key=lambda item: Decimal(str(item.get("price_card_hours_per_gpu_hour") or item.get("price") or 0)),
                reverse=True,
            )
        total = len(items)
        start = (page - 1) * page_size
        return success({"items": items[start:start + page_size], "total": total, "page": page, "page_size": page_size})

    total = q.count()
    products = q.offset((page - 1) * page_size).limit(page_size).all()
    platform_fulfiller_ids, suppliers = _product_serialization_context(products, db)
    items = [
        _product_out(
            product,
            db,
            source_states,
            platform_fulfiller_ids=platform_fulfiller_ids,
            suppliers=suppliers,
        )
        for product in products
    ]
    return success({"items": items, "total": total, "page": page, "page_size": page_size})


@router.get("/filters")
def filters(db: Session = Depends(get_db)):
    regions = [{"code": r["code"], "name": r["name"]} for r in REGIONS]
    return success({"regions": regions})


@router.get("/quote/overview")
def quote_overview(db: Session = Depends(get_db)):
    """KAI-only current cross-section; observations are not inventory."""
    current_products = _current_product_query(
        db, include_merchants=False,
    ).filter(Product.market_source == "kai").all()
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
    products = _current_product_query(
        db, source_states, include_merchants=False,
    ).filter(Product.market_source == "kai").all()
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
    if product_market_source(p) == "wod":
        if settings.THIRD_PARTY_MERCHANT_PUBLIC_CATALOG_ENABLED is not True:
            raise BizError("商品不存在", status_code=404)
        approved_supplier = db.query(Supplier.id).filter(
            Supplier.id == p.supplier_id,
            Supplier.status == "approved",
        ).first()
        if approved_supplier is None:
            # Keep rejected, revoked and still-pending merchant inventory in
            # the owner's management view without exposing a public dead card
            # through a guessed product id.
            raise BizError("商品不存在", status_code=404)
    return success(_product_out(p, db))


@router.get("/{pid}/price-trend")
def price_trend(pid: int, db: Session = Depends(get_db)):
    p = db.query(Product).filter(Product.id == pid).first()
    if not p:
        raise BizError("商品不存在", status_code=404)
    if (
        product_market_source(p) == "wod"
        and settings.THIRD_PARTY_MERCHANT_PUBLIC_CATALOG_ENABLED is not True
    ):
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
