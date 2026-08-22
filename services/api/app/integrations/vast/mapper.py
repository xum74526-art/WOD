"""Vast.ai offer → WOD 内部字段映射。"""
from decimal import Decimal

from app.core.config import settings
from app.services.gpu_catalog import canonicalize_gpu
from app.services.region_mapper import map_region

# Vast gpu_name → WOD gpu_model 标准化
GPU_NORMALIZE = {
    "RTX 4090": "RTX4090",
    "RTX 4090D": "RTX4090",
    "RTX 4080": "RTX4080",
    "RTX 5090": "RTX5090",
    "Tesla V100": "V100",
    "RTX 3090": "RTX3090",
    "RTX PRO 6000 WS": "A6000",
    "A100": "A100",
    "H100": "H100",
    "L40S": "L40S",
}


def normalize_gpu(name: str | None) -> str | None:
    if not name:
        return None
    # The shared catalog keeps materially different SKUs (for example 4090
    # and 4090D, or RTX PRO 6000 and A6000) separate.  The legacy fallback is
    # retained only for provider spellings not yet covered by the catalog.
    return canonicalize_gpu(name) or GPU_NORMALIZE.get(name.strip())


def parse_offer(o: dict) -> dict:
    geo = o.get("geolocation") or ""
    # geolocation 形如 "Texas, US" 或 ", CN"
    parts = [p.strip() for p in geo.split(",")]
    country = parts[-1] if parts else None
    region_code, region_name = map_region(geo, country)
    return {
        "gpu_model": normalize_gpu(o.get("gpu_name")),
        "gpu_name": o.get("gpu_name"),
        "gpu_ram_mb": o.get("gpu_ram"),
        "dph_total": Decimal(str(o.get("dph_total", 0))),  # whole-machine USD/h
        "price_gpu_hour": (
            Decimal(str(o.get("dph_total", 0))) / Decimal(str(o.get("num_gpus") or 1))
        ),
        "geolocation": geo,
        "country_code": country,
        "region_code": region_code,
        "region_name": region_name,
        "reliability": o.get("reliability"),
        "num_gpus": o.get("num_gpus"),
    }


def usd_to_cny(usd) -> Decimal:
    from app.services.market_sync import get_usd_cny_rate

    rate, _, _ = get_usd_cny_rate()
    return Decimal(str(usd)) * rate
