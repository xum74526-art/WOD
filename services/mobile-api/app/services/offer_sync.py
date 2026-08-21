"""Mirror current official provider offers into product cards.

Market charts and source health are maintained by ``market_sync``. This
module only updates the corresponding resource cards. AutoDL and Vast.ai
remain independent: a missing credential or outage at one provider must
never prevent the other provider from refreshing.
"""

from __future__ import annotations

from collections import defaultdict
from decimal import Decimal
from threading import Lock
from typing import Any, Callable

import httpx
from sqlalchemy.orm import Session

from app.core.config import settings
from app.db.session import SessionLocal
from app.models.product import Product
from app.services.gpu_catalog import canonicalize_gpu, normalize_gpu_variant
from app.services.market_sync import get_usd_cny_rate, utcnow
from app.services.purchase_cycles import PURCHASE_CYCLE_DAYS
from app.services.region_mapper import map_region


_OFFER_SYNC_LOCK = Lock()


def _fetch_autodl_offers() -> list[dict[str, Any]]:
    if not settings.AUTODL_TOKEN:
        raise RuntimeError("credentials_missing")
    with httpx.Client(timeout=30, follow_redirects=True) as client:
        response = client.post(
            f"{settings.AUTODL_API_BASE_URL.rstrip('/')}/api/v1/machine/list",
            headers={"Authorization": settings.AUTODL_TOKEN, "Content-Type": "application/json"},
            json={"page_index": 1, "page_size": 500, "charge_type": "payg"},
        )
        response.raise_for_status()
        payload = response.json()
    if payload.get("code") != "Success":
        raise RuntimeError("upstream_rejected")
    return payload.get("data", {}).get("list", [])


def _autodl_groups(offers: list[dict[str, Any]]) -> dict[tuple[str, str, str], dict[str, Any]]:
    groups: dict[tuple[str, str, str], dict[str, Any]] = defaultdict(lambda: {
        "price": None,
        "name": "",
        "region": "",
        "stock": 0,
    })
    for offer in offers:
        model = canonicalize_gpu(offer.get("gpu_name"))
        idle = max(int(offer.get("gpu_idle_num") or 0), 0)
        price = Decimal(str(offer.get("payg_price") or 0)) / Decimal("1000")
        memory_bytes = Decimal(str(offer.get("gpu_memory") or 0))
        memory_gb = float(memory_bytes / Decimal(1024 ** 3)) if memory_bytes > 0 else 0
        variant = normalize_gpu_variant(model, memory_gb)
        region = str(offer.get("region_name") or "")
        if not model or not variant or idle <= 0 or price <= 0:
            continue
        group = groups[(model, variant, region)]
        group["stock"] += idle
        if group["price"] is None or price < group["price"]:
            group["price"] = price
            group["name"] = str(offer.get("gpu_name") or model)
            group["region"] = region
    return dict(groups)


def _upsert_autodl_products(groups: dict[tuple[str, str, str], dict[str, Any]]) -> int:
    db: Session = SessionLocal()
    now = utcnow()
    updated = 0
    try:
        for (model, variant, _), data in groups.items():
            region_code, region_name = map_region(data["region"], "CN")
            product = db.query(Product).filter(
                Product.gpu_model == model,
                Product.memory == variant,
                Product.source_price.isnot(None),
                Product.source_currency == "CNY",
                Product.city == data["region"],
                Product.status == "on",
            ).order_by(Product.id.asc()).first()
            if not product:
                product = Product(
                    name=data["name"], gpu_model=model, memory=variant, cuda=None,
                    price=data["price"], cycle=list(PURCHASE_CYCLE_DAYS),
                    desc="AutoDL 官方接口报价", image_url=f"/static/gpu/{model}.jpg",
                    region_code=region_code, region_name=region_name, country_code="CN",
                    city=data["region"], source_price=data["price"], source_currency="CNY",
                    exchange_rate=Decimal("1"), price_updated_at=now, stock=data["stock"],
                    # AutoDL exposes no reliability metric in this response.
                    # Zero is an explicit "not provided" sentinel.
                    reliability=0, status="on",
                )
                db.add(product)
            else:
                product.name = data["name"]
                product.price = data["price"]
                product.source_price = data["price"]
                product.exchange_rate = Decimal("1")
                product.region_code = region_code
                product.region_name = region_name
                product.country_code = "CN"
                product.city = data["region"]
                product.price_updated_at = now
                product.stock = data["stock"]
                product.reliability = 0
                product.desc = "AutoDL 官方接口报价"
                product.image_url = f"/static/gpu/{model}.jpg"
            updated += 1
        db.commit()
        return updated
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


def _sync_autodl_products() -> dict[str, Any]:
    groups = _autodl_groups(_fetch_autodl_offers())
    return {
        "status": "live" if groups else "empty",
        "upserted": _upsert_autodl_products(groups) if groups else 0,
    }


def _vast_groups(offers: list[dict[str, Any]]) -> dict[tuple[str, str, str], dict[str, Any]]:
    from app.integrations.vast.mapper import parse_offer

    groups: dict[tuple[str, str, str], dict[str, Any]] = defaultdict(lambda: {
        "price_usd": None,
        "name": "",
        "region_code": "",
        "region_name": "",
        "country_code": "",
        "city": "",
        "stock": 0,
        "reliability": 0.0,
    })
    for offer in offers:
        parsed = parse_offer(offer)
        model = parsed.get("gpu_model")
        memory_mb = Decimal(str(parsed.get("gpu_ram_mb") or 0))
        variant = normalize_gpu_variant(
            model,
            float(memory_mb / Decimal(1024)) if memory_mb > 0 else None,
        )
        price = Decimal(str(parsed.get("price_gpu_hour") or 0))
        stock = max(int(parsed.get("num_gpus") or 0), 0)
        city = str(parsed.get("geolocation") or "")
        if not model or not variant or price <= 0 or stock <= 0:
            continue
        group = groups[(model, variant, city)]
        group["stock"] += stock
        if group["price_usd"] is None or price < group["price_usd"]:
            reliability = float(parsed.get("reliability") or 0)
            if 0 < reliability <= 1:
                reliability *= 100
            group.update({
                "price_usd": price,
                "name": str(parsed.get("gpu_name") or model),
                "region_code": parsed.get("region_code") or "",
                "region_name": parsed.get("region_name") or "",
                "country_code": parsed.get("country_code") or "",
                "city": city,
                "reliability": reliability if 0 < reliability <= 100 else 0.0,
            })
    return dict(groups)


def _upsert_vast_products(groups: dict[tuple[str, str, str], dict[str, Any]]) -> int:
    if not groups:
        return 0
    exchange_rate, _, _ = get_usd_cny_rate()
    db: Session = SessionLocal()
    now = utcnow()
    updated = 0
    try:
        for (model, variant, _), data in groups.items():
            price_cny = (data["price_usd"] * exchange_rate).quantize(Decimal("0.0001"))
            product = db.query(Product).filter(
                Product.gpu_model == model,
                Product.memory == variant,
                Product.source_price.isnot(None),
                Product.source_currency == "USD",
                Product.city == data["city"],
                Product.status == "on",
            ).order_by(Product.id.asc()).first()
            if not product:
                product = Product(
                    name=data["name"], gpu_model=model, memory=variant, cuda=None,
                    price=price_cny, cycle=list(PURCHASE_CYCLE_DAYS),
                    desc="Vast.ai 官方接口报价", image_url=f"/static/gpu/{model}.jpg",
                    region_code=data["region_code"], region_name=data["region_name"],
                    country_code=data["country_code"], city=data["city"],
                    source_price=data["price_usd"], source_currency="USD",
                    exchange_rate=exchange_rate, price_updated_at=now, stock=data["stock"],
                    reliability=data["reliability"], status="on",
                )
                db.add(product)
            else:
                product.name = data["name"]
                product.price = price_cny
                product.source_price = data["price_usd"]
                product.exchange_rate = exchange_rate
                product.region_code = data["region_code"]
                product.region_name = data["region_name"]
                product.country_code = data["country_code"]
                product.city = data["city"]
                product.price_updated_at = now
                product.stock = data["stock"]
                product.reliability = data["reliability"]
                product.desc = "Vast.ai 官方接口报价"
                product.image_url = f"/static/gpu/{model}.jpg"
            updated += 1
        db.commit()
        return updated
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


def _sync_vast_products() -> dict[str, Any]:
    from app.integrations.vast.client import fetch_bundles

    groups = _vast_groups(fetch_bundles())
    return {
        "status": "live" if groups else "empty",
        "upserted": _upsert_vast_products(groups) if groups else 0,
    }


def _sync_error_code(exc: Exception) -> str:
    if str(exc) == "credentials_missing":
        return "credentials_missing"
    if isinstance(exc, httpx.HTTPStatusError):
        status = exc.response.status_code
        if status in (401, 403):
            return "authentication_failed"
        if status == 429:
            return "rate_limited"
    if isinstance(exc, httpx.TimeoutException):
        return "upstream_timeout"
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
        # These calls are intentionally independent. In particular, AutoDL
        # credential failures must not short-circuit the Vast.ai refresh.
        return {
            "autodl": _run_provider("autodl", _sync_autodl_products),
            "vast": _run_provider("vast", _sync_vast_products),
        }
    finally:
        _OFFER_SYNC_LOCK.release()
