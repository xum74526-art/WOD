from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.config import settings
from app.services import manual_kyc
from app.db import get_db
from app.models import CommunityPost, MerchantServer, Product
from app.providers import integration_descriptors
from app.responses import ok
from app.security import ApiError
from app.services import resources as resource_service
from app.services.market_snapshots import (
    GETDEPLOYING_SOURCE_URL,
    GETDEPLOYING_PRICE_INDEX_URL,
    daily_market_candles,
    getdeploying_configured,
    load_getdeploying_payload_cache,
    load_getdeploying_public_snapshot,
    market_summary_from_payload,
)

router = APIRouter(prefix="/api/v1/public", tags=["public"])

def _payment_mode() -> str:
    descriptor = integration_descriptors()["payment"]
    return descriptor["provider"] if descriptor["configured"] else "local_placeholder"

@router.get("/status")
def integration_status():
    providers = integration_descriptors()
    return ok({
        "market": "getdeploying_api" if getdeploying_configured() else "getdeploying_public_snapshot",
        "community": "waiting_for_worker",
        "integrations": {
            "kai": bool(settings.KAI_AUTH_CLIENT_ID and settings.KAI_AUTH_CALLBACK_URL),
            "sms": settings.SMS_PROVIDER_ENABLED,
            "email_verification": settings.EMAIL_VERIFICATION_ENABLED,
            "payment": providers["payment"]["configured"],
            "kyc": manual_kyc.provider_descriptor()["configured"],
            "object_storage": providers["object_storage"]["configured"],
        },
    })


@router.get("/products")
def products(db: Session = Depends(get_db)):
    rows = db.query(Product).filter(Product.status == "published").order_by(Product.created_at.desc()).limit(50).all()
    from app.services.agents import hardware_is_current, refresh_presence

    result = []
    for row in rows:
        server = db.query(MerchantServer).filter(MerchantServer.product_id == row.id).first()
        if server is not None:
            refresh_presence(server)
        server_online = bool(server and server.status == "online" and hardware_is_current(server))
        result.append({
        "id": row.id,
        "name": row.name,
        "gpu_model": row.gpu_model,
        "memory": row.memory,
        "region": row.region,
        "description": row.description,
        "gpu_memory_gb": row.gpu_memory_gb,
        "cpu_cores": row.cpu_cores,
        "ram_gb": row.ram_gb,
        "disk_gb": row.disk_gb,
        "bandwidth_mbps": row.bandwidth_mbps,
        "unit_price_ch": float(row.unit_price),
        "price": {"amount": format(row.unit_price, "f"), "currency": row.price_currency, "unit": row.price_unit},
        "total_quantity": row.total_quantity,
        "available_quantity": resource_service.available_quantity(db, row),
        "source_name": row.source_name,
        "source_observed_at": row.source_observed_at,
        "server_online": server_online,
    })
    return ok(result, {
        "count": len(result),
        "real_data_only": True,
        "server_rental_available": True,
        "payment_mode": _payment_mode(),
    })


@router.get("/products/{product_id}")
def product_detail(product_id: int, db: Session = Depends(get_db)):
    row = db.query(Product).filter(Product.id == product_id, Product.status == "published").first()
    if not row:
        raise ApiError("PRODUCT_NOT_FOUND", "算力资源不存在或尚未发布", 404)
    from app.services.agents import hardware_is_current, refresh_presence

    server = db.query(MerchantServer).filter(MerchantServer.product_id == row.id).first()
    if server is not None:
        refresh_presence(server)
    server_online = bool(server and server.status == "online" and hardware_is_current(server))
    return ok({
        "id": row.id,
        "name": row.name,
        "gpu_model": row.gpu_model,
        "memory": row.memory,
        "region": row.region,
        "description": row.description,
        "gpu_memory_gb": row.gpu_memory_gb,
        "cpu_cores": row.cpu_cores,
        "ram_gb": row.ram_gb,
        "disk_gb": row.disk_gb,
        "bandwidth_mbps": row.bandwidth_mbps,
        "unit_price_ch": float(row.unit_price),
        "price": {"amount": format(row.unit_price, "f"), "currency": row.price_currency, "unit": row.price_unit},
        "total_quantity": row.total_quantity,
        "available_quantity": resource_service.available_quantity(db, row),
        "source_name": row.source_name,
        "source_observed_at": row.source_observed_at,
        "server_online": server_online,
    }, {
        "real_data_only": True,
        "server_rental_available": server_online,
        "payment_mode": _payment_mode(),
    })


def _getdeploying_market_payload() -> dict:
    payload = load_getdeploying_payload_cache()
    if payload is not None:
        return payload
    public_snapshot = load_getdeploying_public_snapshot()
    if public_snapshot is not None:
        return public_snapshot
    raise ApiError(
        "GETDEPLOYING_MARKET_UNAVAILABLE",
        "GetDeploying 公开行情快照不可用，请重新同步数据",
        503,
    )


@router.get("/market/summary")
def market_summary():
    payload = _getdeploying_market_payload()
    markets = market_summary_from_payload(payload)
    return ok(markets, {
        "count": len(markets),
        "source": "GetDeploying",
        "source_url": payload.get("source_url") or GETDEPLOYING_SOURCE_URL,
        "observed_at": payload.get("observed_at"),
        "currency": "USD",
        "unit": "GPU/hour",
        "snapshot_frozen": payload.get("source_mode") == "public_page_snapshot",
        "history_updated_at": payload.get("source_updated_at"),
        "history_source_url": GETDEPLOYING_PRICE_INDEX_URL,
        "attribution": "GetDeploying GPU Rental Price Index",
        "aggregation": "public_weekly_median_price",
    })


@router.get("/market/candles")
def market_candles(
    gpu_model: str = Query(min_length=1, max_length=64),
    days: int = Query(default=30, ge=1, le=365),
    db: Session = Depends(get_db),
):
    candles = daily_market_candles(db, gpu_model, days=days)
    return ok(candles, {
        "source": "GetDeploying hourly price snapshots",
        "gpu_model": gpu_model,
        "days": days,
        "currency": "USD",
        "unit": "GPU/hour",
        "timezone": "UTC",
        "aggregation": "daily_ohlc_from_hourly_median_quotes",
    })


@router.get("/market")
def market(gpu_model: str | None = Query(default=None, max_length=64), db: Session = Depends(get_db)):
    query = db.query(Product).filter(Product.status == "published", Product.source_observed_at.isnot(None))
    if gpu_model:
        query = query.filter(Product.gpu_model == gpu_model)
    rows = query.order_by(Product.source_observed_at.desc()).limit(100).all()
    return ok([{
        "product_id": row.id,
        "gpu_model": row.gpu_model,
        "memory": row.memory,
        "price_ch": float(row.unit_price),
        "price": {"amount": format(row.unit_price, "f"), "currency": row.price_currency, "unit": row.price_unit},
        "source": row.source_name,
        "observed_at": row.source_observed_at,
    } for row in rows], {"count": len(rows), "real_data_only": True})


@router.get("/community")
def community(db: Session = Depends(get_db)):
    rows = db.query(CommunityPost).filter(
        CommunityPost.rights_status == "link_summary_allowed"
    ).order_by(CommunityPost.published_at.desc()).limit(10).all()
    return ok([{
        "id": row.id,
        "title": row.title,
        "summary": row.summary,
        "content_type": row.content_type,
        "source_name": row.source_name,
        "source_url": row.source_url,
        "published_at": row.published_at,
    } for row in rows], {"count": len(rows), "rights_filtered": True})
