"""Mirror current KAI quotes into product cards.

Market charts and source health are maintained by ``market_sync``. KAI is the
only active third-party market source. Retired provider rows are retained for
historical order/audit references, but are always soft-disabled.
"""

from __future__ import annotations

from decimal import Decimal
from threading import Lock
from typing import Any, Callable

from sqlalchemy.orm import Session

from app.core.config import settings
from app.db.session import SessionLocal
from app.integrations.kai_pricing import (
    KaiPricingError,
    fetch_price_batch,
    normalized_current_quotes,
)
from app.models.product import Product
from app.services.region_mapper import map_region


_OFFER_SYNC_LOCK = Lock()


def _upsert_kai_products(quotes: list[dict[str, Any]]) -> int:
    """Publish current KAI prices without replenishing platform allocation."""

    db: Session = SessionLocal()
    updated = 0
    try:
        accepted_ids: set[str] = set()
        for data in quotes:
            # KAI's gpuCountOptions describes the largest order configuration,
            # not current machine inventory. Empty options cannot be sold.
            max_quantity = data.get("max_configurable_quantity")
            if not isinstance(max_quantity, int) or max_quantity <= 0:
                continue
            external_id = data["external_product_id"]
            accepted_ids.add(external_id)
            region_code, region_name = map_region(data["region"])
            product = db.query(Product).filter(
                Product.market_source == "kai",
                Product.external_product_id == external_id,
            ).order_by(Product.id.asc()).first()
            initial_cap = min(max(int(settings.KAI_CLOSED_TEST_INITIAL_STOCK), 0), max_quantity)
            if not product:
                product = Product(
                    name=data["display_name"], gpu_model=data["gpu_model"],
                    memory=data["gpu_variant"], cuda=None,
                    price=data["price_cny"], cycle=[],
                    desc=(
                        "KAI Pricing 当前卡时报价；可购数量为平台人工履约额度，"
                        "上游数量仅表示单次最大可配置量，不是实时库存"
                    ),
                    image_url=f"/static/gpu/{data['gpu_model']}.jpg",
                    region_code=region_code, region_name=region_name,
                    country_code=None, city=data["region"],
                    market_source="kai", external_product_id=external_id,
                    stock_semantics="platform_closed_test_manual_fulfillment_allocation",
                    source_max_configurable_quantity=max_quantity,
                    platform_stock_cap=initial_cap,
                    source_price=data["price_cny"], source_currency="CNY",
                    exchange_rate=Decimal("1"), price_updated_at=data["observed_at"],
                    stock=initial_cap, reliability=0, status="on",
                )
                db.add(product)
            else:
                product.name = data["display_name"]
                product.gpu_model = data["gpu_model"]
                product.memory = data["gpu_variant"]
                product.price = data["price_cny"]
                product.cycle = []
                product.source_price = data["price_cny"]
                product.source_currency = "CNY"
                product.exchange_rate = Decimal("1")
                product.region_code = region_code
                product.region_name = region_name
                product.country_code = None
                product.city = data["region"]
                product.price_updated_at = data["observed_at"]
                product.source_max_configurable_quantity = max_quantity
                if product.platform_stock_cap is None:
                    product.platform_stock_cap = initial_cap
                # ``stock`` is a consumed/restored platform allocation.  A
                # market refresh may clamp legacy bad data but never top it up.
                product.stock = min(
                    max(int(product.stock or 0), 0),
                    max(int(product.platform_stock_cap or 0), 0),
                )
                product.reliability = 0
                product.status = "on"
                product.stock_semantics = "platform_closed_test_manual_fulfillment_allocation"
                product.desc = (
                    "KAI Pricing 当前卡时报价；可购数量为平台人工履约额度，"
                    "上游数量仅表示单次最大可配置量，不是实时库存"
                )
                product.image_url = f"/static/gpu/{data['gpu_model']}.jpg"
            updated += 1
        stale = db.query(Product).filter(Product.market_source == "kai")
        if accepted_ids:
            stale = stale.filter(Product.external_product_id.notin_(accepted_ids))
        for product in stale.all():
            product.status = "off"
        # Retired provider rows remain available to historical orders and audit
        # queries, but are never listed or purchasable.
        for product in db.query(Product).filter(
            Product.market_source.in_(["autodl", "vast"]),
        ).all():
            product.status = "off"
            product.stock = 0
        db.commit()
        return updated
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


def _sync_kai_products() -> dict[str, Any]:
    batch = fetch_price_batch()
    quotes = normalized_current_quotes(batch)
    sellable = [item for item in quotes if item.get("max_configurable_quantity")]
    return {
        "status": "live" if sellable else "empty",
        "upserted": _upsert_kai_products(sellable),
    }


def _sync_error_code(exc: Exception) -> str:
    if isinstance(exc, KaiPricingError):
        return exc.code
    if str(exc) == "credentials_missing":
        return "credentials_missing"
    return "upstream_error"


def _run_provider(name: str, callback: Callable[[], dict[str, Any]]) -> dict[str, Any]:
    try:
        result = callback()
        print(f"[offer_sync] {name}: {result['status']} ({result['upserted']} models)")
        return result
    except Exception as exc:  # noqa: BLE001
        # Never put exception messages, request headers, or credentials in logs.
        code = _sync_error_code(exc)
        print(f"[offer_sync] {name}: {code}")
        return {"status": "error", "error_code": code, "upserted": 0}


def sync_offers() -> dict[str, dict[str, Any]]:
    if not _OFFER_SYNC_LOCK.acquire(blocking=False):
        return {"status": {"status": "skipped", "reason": "already_running"}}
    try:
        return {"kai": _run_provider("kai", _sync_kai_products)}
    finally:
        _OFFER_SYNC_LOCK.release()
