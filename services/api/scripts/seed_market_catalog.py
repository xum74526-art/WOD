"""Create a large, clearly labelled local demo server catalog from GPU market data."""

from __future__ import annotations

import argparse
import json
from datetime import datetime, timedelta, timezone
from decimal import Decimal, ROUND_HALF_UP
from pathlib import Path

from sqlalchemy.engine import make_url
from sqlalchemy.orm import Session

from app.config import settings
from app.db import SessionLocal
from app.models import (
    MerchantServer,
    Product,
    ProductPriceVersion,
    ProductReviewEvent,
    SupplierApplication,
    SupplierProfile,
    User,
)
from app.services.agents import synthetic_inventory, synthetic_service_checks
from app.services.market_snapshots import (
    load_getdeploying_payload_cache,
    load_getdeploying_public_snapshot,
    market_summary_from_payload,
)


RESOURCE_PREFIX = "PRMKTDEMO"
SERVER_PREFIX = "SVMKTDEMO"
ADMIN_EMAIL = "market-demo-admin@example.com"
SUPPLIER_EMAIL_PREFIX = "market-demo-supplier"

SUPPLIERS = (
    ("星云算力（演示）", "华东·上海"),
    ("矩阵智算（演示）", "华北·北京"),
    ("极光云图（演示）", "华南·深圳"),
    ("西部算谷（演示）", "西北·西安"),
    ("天府智算（演示）", "西南·成都"),
    ("滨海超算（演示）", "华北·天津"),
    ("钱塘计算（演示）", "华东·杭州"),
    ("南粤算力（演示）", "华南·广州"),
)

REGIONS = (
    "华东·上海",
    "华北·北京",
    "华南·深圳",
    "西北·西安",
    "西南·成都",
    "华东·杭州",
    "华北·天津",
    "华南·广州",
    "西南·重庆",
    "西北·兰州",
)

MEMORY_BY_SLUG = {
    "nvidia-h100": 80,
    "nvidia-a100": 80,
    "nvidia-h200": 141,
    "nvidia-l40s": 48,
    "nvidia-rtx-pro-6000": 96,
    "nvidia-v100": 32,
    "nvidia-l4": 24,
    "nvidia-b200": 192,
    "nvidia-rtx-4090": 24,
    "nvidia-a6000": 48,
    "nvidia-b300": 288,
    "nvidia-l40": 48,
    "nvidia-a10": 24,
    "nvidia-rtx-6000-ada": 48,
    "nvidia-rtx-5090": 32,
    "nvidia-t4": 16,
    "nvidia-a4000": 16,
    "nvidia-a5000": 24,
    "nvidia-rtx-3090": 24,
    "nvidia-rtx-4000-ada": 20,
    "amd-mi300x": 192,
    "nvidia-rtx-4080": 16,
    "nvidia-p100": 16,
    "nvidia-rtx-3080-ti": 12,
    "nvidia-a40": 48,
    "nvidia-rtx-3070": 8,
    "nvidia-rtx-6000": 24,
}

IMAGE_BY_SLUG = {
    "nvidia-h100": "H100.jpg",
    "nvidia-a100": "A100.jpg",
    "nvidia-h200": "H200.jpg",
    "nvidia-l40s": "L40S.jpg",
    "nvidia-rtx-pro-6000": "RTXPRO6000.jpg",
    "nvidia-v100": "V100.jpg",
    "nvidia-l4": "L4.jpg",
    "nvidia-b200": "B200.jpg",
    "nvidia-rtx-4090": "RTX4090.jpg",
    "nvidia-a6000": "A6000.jpg",
    "nvidia-b300": "B300.jpg",
    "nvidia-l40": "L40.jpg",
    "nvidia-a10": "A10.jpg",
    "nvidia-rtx-6000-ada": "RTX6000Ada.jpg",
    "nvidia-rtx-5090": "RTX5090.jpg",
    "nvidia-t4": "T4.jpg",
    "nvidia-a4000": "A4000.jpg",
    "nvidia-a5000": "A5000.jpg",
    "nvidia-rtx-3090": "RTX3090.jpg",
    "nvidia-rtx-4000-ada": "RTX4000Ada.jpg",
    "amd-mi300x": "MI300X.jpg",
    "nvidia-rtx-4080": "RTX4080.jpg",
    "nvidia-p100": "P100.jpg",
    "nvidia-rtx-3080-ti": "RTX3080Ti.jpg",
    "nvidia-a40": "A40.jpg",
    "nvidia-rtx-3070": "RTX3070.jpg",
    "nvidia-rtx-6000": "RTXPRO6000.jpg",
}

PRICE_FACTORS = (
    Decimal("0.88"),
    Decimal("0.93"),
    Decimal("0.97"),
    Decimal("1.00"),
    Decimal("1.04"),
    Decimal("1.09"),
    Decimal("1.15"),
)


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _is_local_database() -> bool:
    url = make_url(settings.DATABASE_URL)
    if url.drivername.startswith("sqlite"):
        return True
    if url.host in {"127.0.0.1", "localhost", "::1"}:
        return True
    return (
        settings.APP_ENV.casefold() == "development"
        and url.host == "postgres"
        and Path("/.dockerenv").exists()
    )


def derive_price(median_price: object, index: int) -> Decimal:
    """Create deterministic offer variation around the observed market median."""
    market_price = Decimal(str(median_price or "0"))
    if market_price <= 0:
        market_price = Decimal("0.50")
    value = market_price * PRICE_FACTORS[index % len(PRICE_FACTORS)]
    return max(Decimal("0.05"), value).quantize(Decimal("0.001"), rounding=ROUND_HALF_UP)


def derive_spec(gpu_slug: str, median_price: object, index: int) -> dict[str, int]:
    """Generate plausible single-GPU host specs without claiming real inventory."""
    memory = MEMORY_BY_SLUG.get(gpu_slug, 24)
    price = float(median_price or 0)
    if price >= 4 or memory >= 141:
        cpu, ram = 96, max(512, memory * 4)
    elif price >= 1.5 or memory >= 80:
        cpu, ram = 64, max(256, memory * 4)
    elif memory >= 40:
        cpu, ram = 48, max(192, memory * 4)
    elif memory >= 24:
        cpu, ram = 32, 128
    else:
        cpu, ram = 24, 96
    disk_options = (960, 1920, 3840, 7680)
    bandwidth_options = (200, 500, 1000, 2000)
    return {
        "gpu_memory_gb": memory,
        "cpu_cores": cpu,
        "ram_gb": ram,
        "disk_gb": disk_options[index % len(disk_options)],
        "bandwidth_mbps": bandwidth_options[(index // 2) % len(bandwidth_options)],
    }


def _upsert_user(db: Session, *, email: str, display_name: str, role: str) -> User:
    row = db.query(User).filter(User.email == email).first()
    if row is None:
        row = User(email=email, display_name=display_name)
        db.add(row)
    row.display_name = display_name
    row.email_verified = True
    row.role = role
    row.status = "active"
    db.flush()
    return row


def _upsert_supplier(db: Session, index: int, name: str, region: str, admin: User, now: datetime) -> User:
    supplier = _upsert_user(
        db,
        email=f"{SUPPLIER_EMAIL_PREFIX}-{index + 1:02d}@example.com",
        display_name=name,
        role="supplier",
    )
    application = db.query(SupplierApplication).filter(SupplierApplication.user_id == supplier.id).first()
    if application is None:
        application = SupplierApplication(
            user_id=supplier.id,
            company_name=name,
            contact_name="演示联系人",
            contact_phone=f"1399000{index + 1:04d}",
        )
        db.add(application)
    application.company_name = name
    application.contact_name = "演示联系人"
    application.contact_phone = f"1399000{index + 1:04d}"
    application.region = region
    application.description = "本地开发演示商家，由批量算力市场种子脚本生成。"
    application.status = "approved"
    application.review_note = "开发演示数据自动批准"
    application.reviewed_by = admin.id
    application.reviewed_at = now
    application.version = max(1, application.version or 1)

    profile = db.query(SupplierProfile).filter(SupplierProfile.user_id == supplier.id).first()
    if profile is None:
        profile = SupplierProfile(
            user_id=supplier.id,
            store_name=name,
            contact_name="演示联系人",
            contact_phone=f"1399000{index + 1:04d}",
        )
        db.add(profile)
    profile.store_name = name
    profile.contact_name = "演示联系人"
    profile.contact_phone = f"1399000{index + 1:04d}"
    profile.service_regions = [region]
    profile.introduction = "仅用于 KAI 本地开发与界面测试的演示算力供应商。"
    profile.version = max(1, profile.version or 1)
    db.flush()
    return supplier


def _market_rows() -> list[dict]:
    payload = load_getdeploying_payload_cache() or load_getdeploying_public_snapshot()
    if payload is None:
        raise RuntimeError("GetDeploying market snapshot is unavailable")
    rows = market_summary_from_payload(payload)
    if not rows:
        raise RuntimeError("GetDeploying market snapshot contains no GPU rows")
    return rows


def seed_market_catalog(db: Session, *, count: int = 120) -> dict:
    now = _now()
    market_rows = _market_rows()
    admin = _upsert_user(db, email=ADMIN_EMAIL, display_name="算力市场演示管理员", role="admin")
    suppliers = [
        _upsert_supplier(db, index, name, region, admin, now)
        for index, (name, region) in enumerate(SUPPLIERS)
    ]

    created = 0
    updated = 0
    represented_models: set[str] = set()
    for index in range(count):
        market = market_rows[index % len(market_rows)]
        gpu_model = str(market["gpu_model"])
        gpu_slug = str(market["gpu_slug"])
        spec = derive_spec(gpu_slug, market.get("median_price"), index)
        price = derive_price(market.get("median_price"), index)
        region = REGIONS[(index * 3) % len(REGIONS)]
        supplier_index = (index * 5) % len(suppliers)
        supplier = suppliers[supplier_index]
        supplier_name = SUPPLIERS[supplier_index][0]
        resource_no = f"{RESOURCE_PREFIX}{index + 1:04d}"
        server_no = f"{SERVER_PREFIX}{index + 1:04d}"
        row = db.query(Product).filter(Product.resource_no == resource_no).first()
        if row is None:
            row = Product(resource_no=resource_no, name="", gpu_model="", memory="", description="", unit_price=price)
            db.add(row)
            created += 1
        else:
            updated += 1

        row.supplier_id = supplier.id
        row.name = f"{region} · {gpu_model} {spec['gpu_memory_gb']}GB 独占节点（演示）"
        row.gpu_model = gpu_model
        row.memory = f"{spec['gpu_memory_gb']}GB"
        row.gpu_memory_gb = spec["gpu_memory_gb"]
        row.region = region
        row.cpu_cores = spec["cpu_cores"]
        row.ram_gb = spec["ram_gb"]
        row.disk_gb = spec["disk_gb"]
        row.bandwidth_mbps = spec["bandwidth_mbps"]
        row.image_url = f"/static/gpu/{IMAGE_BY_SLUG[gpu_slug]}"
        row.description = (
            f"开发演示服务器：{gpu_model} 单卡独占，{spec['cpu_cores']} 核 CPU、"
            f"{spec['ram_gb']}GB 内存、{spec['disk_gb']}GB NVMe、"
            f"{spec['bandwidth_mbps']}Mbps 带宽。价格参考 GetDeploying 算力行情中位价后生成，"
            "不代表真实库存或真实商家报价。"
        )
        row.unit_price = price
        row.price_currency = "CNY"
        row.price_unit = "server_hour"
        row.total_quantity = 1
        row.source_name = supplier_name
        row.source_observed_at = now
        row.status = "published"
        row.review_note = "本地开发演示数据自动批准"
        row.reviewed_by = admin.id
        row.reviewed_at = now
        row.published_at = now - timedelta(minutes=index)
        row.version = max(3, row.version or 1)
        db.flush()

        server = db.query(MerchantServer).filter(MerchantServer.product_id == row.id).first()
        if server is None:
            server = MerchantServer(
                server_no=server_no,
                supplier_id=supplier.id,
                product_id=row.id,
                public_host="127.0.0.1",
                ssh_port=22000 + index,
                ssh_username="kai",
            )
            db.add(server)
        server.server_no = server_no
        server.supplier_id = supplier.id
        server.public_host = "127.0.0.1"
        server.ssh_port = 22000 + index
        server.ssh_username = "kai"
        server.status = "online"
        server.agent_mode = "local_simulator"
        server.agent_version = "market-demo/1.0"
        server.agent_platform = "linux"
        server.agent_arch = "amd64"
        server.agent_hostname = f"market-demo-{index + 1:04d}"
        server.agent_capabilities = ["authorize_key", "revoke_key", "cleanup_account", "offline_expiry"]
        server.hardware_inventory = synthetic_inventory(row, observed_at=now)
        server.hardware_observed_at = now
        server.hardware_verified_at = now
        server.hardware_verification_status = "verified"
        server.hardware_mismatches = []
        server.agent_service_checks = synthetic_service_checks(observed_at=now)
        server.agent_service_observed_at = now
        server.agent_service_status = "healthy"
        server.agent_enrolled_at = now
        server.last_seen_at = now
        server.version = max(1, server.version or 1)

        price_version = db.query(ProductPriceVersion).filter(
            ProductPriceVersion.product_id == row.id,
            ProductPriceVersion.version == 1,
        ).first()
        if price_version is None:
            price_version = ProductPriceVersion(product_id=row.id, version=1, changed_by=supplier.id)
            db.add(price_version)
        price_version.amount = price
        price_version.currency = "CNY"
        price_version.price_unit = "server_hour"
        price_version.changed_by = supplier.id
        price_version.change_note = "基于公开算力行情生成的开发演示价格"

        event = db.query(ProductReviewEvent).filter(
            ProductReviewEvent.product_id == row.id,
            ProductReviewEvent.event_type == "development_seed_published",
        ).first()
        if event is None:
            db.add(ProductReviewEvent(
                product_id=row.id,
                actor_user_id=admin.id,
                actor_role="admin",
                event_type="development_seed_published",
                from_status="pending_review",
                to_status="published",
                note="批量算力市场开发演示数据",
                payload={"seed": True, "source": "GetDeploying GPU Rental Price Index"},
            ))
        represented_models.add(gpu_model)

    db.commit()
    return {
        "requested_count": count,
        "created": created,
        "updated": updated,
        "supplier_count": len(suppliers),
        "gpu_model_count": len(represented_models),
        "resource_prefix": RESOURCE_PREFIX,
        "demo_only": True,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Seed a large local demo compute-market catalog.")
    parser.add_argument("--confirm-local", action="store_true", help="Confirm that the local database may be updated.")
    parser.add_argument("--count", type=int, default=120, choices=range(1, 501))
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()
    if not args.confirm_local:
        parser.error("--confirm-local is required")
    if not _is_local_database():
        parser.error("refusing to seed a non-local database")
    with SessionLocal() as db:
        try:
            result = seed_market_catalog(db, count=args.count)
        except Exception:
            db.rollback()
            raise
    if args.json:
        print(json.dumps(result, ensure_ascii=False))
    else:
        print("KAI demo market catalog is ready.")
        print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
