import base64
import binascii
import hashlib
import json
import re
import secrets
from datetime import datetime, timedelta, timezone
from pathlib import Path
from urllib.parse import urlsplit, urlunsplit
from uuid import uuid4

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.agent_schemas import (
    AgentEnrollIn,
    AgentHardwareInventory,
    AgentHeartbeatIn,
    AgentServiceChecks,
)
from app.config import settings
from app.models import (
    AccessLease,
    AgentCommand,
    AgentEnrollmentToken,
    AgentRequestNonce,
    MerchantServer,
    Order,
    Product,
    ProductReviewEvent,
    SupplierApplication,
    User,
)
from app.security import ApiError, digest
from app.services.internal_modules import create_notification


AGENT_VERSION = "0.3.0"
SUPPORTED_CAPABILITIES = {"authorize_key", "revoke_key", "cleanup_account", "offline_expiry"}
AGENT_ROOT = (
    Path(settings.AGENT_ARTIFACT_ROOT).expanduser()
    if settings.AGENT_ARTIFACT_ROOT
    else Path(__file__).resolve().parents[3] / "agent"
)
DIST_ROOT = AGENT_ROOT / "dist"
INSTALL_ROOT = AGENT_ROOT / "install"
DOWNLOAD_TARGETS = (
    ("linux", "amd64", "kai-agent-linux-amd64"),
    ("linux", "arm64", "kai-agent-linux-arm64"),
    ("windows", "amd64", "kai-agent-windows-amd64.exe"),
    ("windows", "arm64", "kai-agent-windows-arm64.exe"),
)


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _aware(value: datetime | None) -> datetime | None:
    if value is None or value.tzinfo is not None:
        return value
    return value.replace(tzinfo=timezone.utc)


def _normalized_gpu_name(value: str) -> str:
    normalized = re.sub(
        r"\b(NVIDIA|GEFORCE|TESLA|QUADRO|GRAPHICS|GPU)\b",
        " ",
        value.upper(),
    )
    return re.sub(r"[^A-Z0-9]+", "", normalized)


def _inventory_dict(inventory: AgentHardwareInventory) -> dict:
    return inventory.model_dump(mode="json")


def synthetic_inventory(product: Product, *, observed_at: datetime | None = None) -> dict:
    now = observed_at or _now()
    return {
        "collected_at": now.isoformat(),
        "source": "local_simulator",
        "os_name": "KAI local development simulator",
        "os_version": "1.0",
        "kernel_version": "simulated",
        "cpu_model": "Simulated CPU",
        "cpu_logical_cores": product.cpu_cores or 1,
        "memory_total_mb": (product.ram_gb or 1) * 1024,
        "disk_total_gb": product.disk_gb or 1,
        "disk_available_gb": product.disk_gb or 1,
        "gpus": [{
            "index": 0,
            "name": product.gpu_model,
            "memory_total_mb": (product.gpu_memory_gb or 1) * 1024,
            "uuid": "LOCAL-SIMULATOR",
            "driver_version": "simulated",
        }],
        "collection_errors": [],
    }


def synthetic_service_checks(*, observed_at: datetime | None = None) -> dict:
    now = observed_at or _now()
    return {
        "checked_at": now.isoformat(),
        "ssh": {"reachable": True, "port": 22, "error": None},
    }


def _compare_inventory(product: Product, inventory: dict) -> list[dict]:
    mismatches: list[dict] = []
    declared_gpu = _normalized_gpu_name(product.gpu_model)
    gpus = inventory.get("gpus") or []
    matching = [
        item for item in gpus
        if declared_gpu and (
            declared_gpu in _normalized_gpu_name(str(item.get("name", "")))
            or _normalized_gpu_name(str(item.get("name", ""))) in declared_gpu
        )
    ]
    if not matching:
        mismatches.append({
            "field": "gpu_model",
            "declared": product.gpu_model,
            "detected": [item.get("name") for item in gpus],
            "message": "未检测到与申报型号一致的 NVIDIA GPU",
        })
    elif product.gpu_memory_gb:
        detected_mb = max(int(item.get("memory_total_mb") or 0) for item in matching)
        required_mb = product.gpu_memory_gb * 1024
        if detected_mb < int(required_mb * 0.98):
            mismatches.append({
                "field": "gpu_memory_gb",
                "declared": product.gpu_memory_gb,
                "detected": round(detected_mb / 1024, 2),
                "message": "实测显存低于申报值",
            })
    detected_cores = int(inventory.get("cpu_logical_cores") or 0)
    if product.cpu_cores and detected_cores < product.cpu_cores:
        mismatches.append({
            "field": "cpu_cores", "declared": product.cpu_cores,
            "detected": detected_cores, "message": "实测逻辑 CPU 核数低于申报值",
        })
    detected_memory_mb = int(inventory.get("memory_total_mb") or 0)
    if product.ram_gb and detected_memory_mb < int(product.ram_gb * 1024 * 0.95):
        mismatches.append({
            "field": "ram_gb", "declared": product.ram_gb,
            "detected": round(detected_memory_mb / 1024, 2), "message": "实测内存低于申报值",
        })
    detected_disk_gb = int(inventory.get("disk_total_gb") or 0)
    if product.disk_gb and detected_disk_gb < int(product.disk_gb * 0.92):
        mismatches.append({
            "field": "disk_gb", "declared": product.disk_gb,
            "detected": detected_disk_gb, "message": "实测磁盘容量低于申报值",
        })
    return mismatches


def _pause_published_product(db: Session, server: MerchantServer, product: Product, status: str) -> None:
    if product.status != "published":
        return
    previous = product.status
    product.status = "approved"
    product.published_at = None
    product.review_note = "Agent 实测配置需要重新核验，服务器已自动暂停出租，请商家检查后重新提交审核。"
    product.version += 1
    db.add(ProductReviewEvent(
        product_id=product.id,
        actor_user_id=server.supplier_id,
        actor_role="system",
        event_type="hardware_auto_unpublished",
        from_status=previous,
        to_status="approved",
        note=product.review_note,
        payload={"hardware_status": status, "mismatches": server.hardware_mismatches or []},
    ))
    create_notification(
        db,
        user_id=server.supplier_id,
        category="review",
        title="服务器已自动暂停出租",
        body=f"服务器 {server.server_no} 的 Agent 实测配置需要重新核验，请检查后重新审核。",
        action_path="/supplier/servers",
    )


def apply_hardware_inventory(
    db: Session,
    server: MerchantServer,
    product: Product,
    inventory: AgentHardwareInventory | dict | None,
    *,
    observed_at: datetime | None = None,
) -> str:
    now = observed_at or _now()
    if inventory is None:
        server.hardware_inventory = {}
        server.hardware_inventory_hash = None
        server.hardware_observed_at = now
        server.hardware_verified_at = None
        server.hardware_verification_status = "unavailable"
        server.hardware_mismatches = [{
            "field": "inventory", "declared": "required", "detected": None,
            "message": "Agent 尚未上报硬件清单，请升级并重新运行 Agent",
        }]
        _pause_published_product(db, server, product, "unavailable")
        return "unavailable"
    raw = _inventory_dict(inventory) if isinstance(inventory, AgentHardwareInventory) else inventory
    encoded = json.dumps(raw, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()
    mismatches = _compare_inventory(product, raw)
    status = "mismatch" if mismatches else "verified"
    server.hardware_inventory = raw
    server.hardware_inventory_hash = hashlib.sha256(encoded).hexdigest()
    server.hardware_observed_at = now
    server.hardware_verified_at = now if status == "verified" else None
    server.hardware_verification_status = status
    server.hardware_mismatches = mismatches
    if status != "verified":
        _pause_published_product(db, server, product, status)
    return status


def hardware_status(server: MerchantServer, *, now: datetime | None = None) -> str:
    status = server.hardware_verification_status or "pending"
    if server.agent_mode == "local_simulator":
        # The simulator is an explicit development-only mode and has no real
        # host to attest. New resources receive a synthetic snapshot; this
        # fallback keeps older local fixtures and pre-migration data usable.
        return "verified" if status == "pending" else status
    observed = _aware(server.hardware_observed_at)
    if status == "verified" and (
        observed is None
        or observed < (now or _now()) - timedelta(seconds=settings.AGENT_HARDWARE_STALE_SECONDS)
    ):
        return "stale"
    return status


def hardware_is_current(server: MerchantServer) -> bool:
    return hardware_status(server) == "verified"


def hardware_out(server: MerchantServer) -> dict:
    return {
        "status": hardware_status(server),
        "observed_at": server.hardware_observed_at,
        "verified_at": server.hardware_verified_at,
        "inventory_hash": server.hardware_inventory_hash,
        "inventory": server.hardware_inventory or {},
        "mismatches": server.hardware_mismatches or [],
        "stale_after_seconds": settings.AGENT_HARDWARE_STALE_SECONDS,
        "is_simulated": server.agent_mode == "local_simulator",
    }


def apply_service_checks(
    db: Session,
    server: MerchantServer,
    product: Product,
    checks: AgentServiceChecks | dict | None,
    *,
    observed_at: datetime | None = None,
) -> str:
    now = observed_at or _now()
    if checks is None:
        raw: dict = {}
        status = "unavailable"
    else:
        raw = checks.model_dump(mode="json") if isinstance(checks, AgentServiceChecks) else checks
        status = "healthy" if bool((raw.get("ssh") or {}).get("reachable")) else "unhealthy"
    server.agent_service_checks = raw
    server.agent_service_observed_at = now
    server.agent_service_status = status
    if status != "healthy":
        _pause_published_product(db, server, product, status)
    return status


def service_status(server: MerchantServer, *, now: datetime | None = None) -> str:
    if server.agent_mode == "local_simulator":
        return "healthy"
    status = server.agent_service_status or "pending"
    observed = _aware(server.agent_service_observed_at)
    if status == "healthy" and (
        observed is None
        or observed < (now or _now()) - timedelta(seconds=settings.AGENT_SERVICE_STALE_SECONDS)
    ):
        return "stale"
    return status


def service_is_current(server: MerchantServer) -> bool:
    return service_status(server) == "healthy"


def service_out(server: MerchantServer) -> dict:
    return {
        "status": service_status(server),
        "observed_at": server.agent_service_observed_at,
        "checks": server.agent_service_checks or {},
        "stale_after_seconds": settings.AGENT_SERVICE_STALE_SECONDS,
        "is_simulated": server.agent_mode == "local_simulator",
    }


def _approved_supplier(db: Session, user: User) -> None:
    approved = db.query(SupplierApplication.id).filter(
        SupplierApplication.user_id == user.id,
        SupplierApplication.status == "approved",
    ).first()
    if user.role != "supplier" or approved is None:
        raise ApiError("SUPPLIER_REQUIRED", "只有已审核商家可以绑定服务器 Agent", 403)


def owned_server(db: Session, user: User, server_id: int, *, lock: bool = False) -> MerchantServer:
    _approved_supplier(db, user)
    query = db.query(MerchantServer).filter(
        MerchantServer.id == server_id,
        MerchantServer.supplier_id == user.id,
    )
    if lock:
        query = query.with_for_update()
    row = query.first()
    if row is None:
        raise ApiError("SERVER_NOT_FOUND", "服务器不存在", 404)
    return row


def api_base_url(request_base_url: str) -> str:
    configured = settings.AGENT_PUBLIC_API_BASE_URL.strip().rstrip("/")
    return configured or request_base_url.rstrip("/")


def _docker_api_url(base_url: str) -> str:
    parsed = urlsplit(base_url)
    if parsed.hostname not in ("127.0.0.1", "localhost"):
        return base_url
    port = f":{parsed.port}" if parsed.port else ""
    return urlunsplit((
        parsed.scheme,
        f"host.docker.internal{port}",
        parsed.path,
        parsed.query,
        parsed.fragment,
    ))


def downloads(base_url: str) -> list[dict]:
    rows = []
    for platform, arch, filename in DOWNLOAD_TARGETS:
        path = DIST_ROOT / filename
        rows.append({
            "platform": platform,
            "arch": arch,
            "filename": filename,
            "url": f"{base_url}/api/v1/agent/downloads/{platform}/{arch}",
            "available": path.is_file(),
            "size_bytes": path.stat().st_size if path.is_file() else None,
            "sha256": hashlib.sha256(path.read_bytes()).hexdigest() if path.is_file() else None,
        })
    docker_context = DIST_ROOT / "kai-agent-docker-context.tar.gz"
    rows.append({
        "platform": "docker",
        "arch": "multi",
        "filename": docker_context.name,
        "url": f"{base_url}/api/v1/agent/downloads/docker/context",
        "available": docker_context.is_file(),
        "size_bytes": docker_context.stat().st_size if docker_context.is_file() else None,
        "sha256": hashlib.sha256(docker_context.read_bytes()).hexdigest()
        if docker_context.is_file() else None,
    })
    return rows


def create_enrollment(
    db: Session,
    user: User,
    server_id: int,
    *,
    expires_in_minutes: int,
    base_url: str,
) -> dict:
    server = owned_server(db, user, server_id, lock=True)
    now = _now()
    db.query(AgentEnrollmentToken).filter(
        AgentEnrollmentToken.server_id == server.id,
        AgentEnrollmentToken.used_at.is_(None),
        AgentEnrollmentToken.revoked_at.is_(None),
    ).update({AgentEnrollmentToken.revoked_at: now}, synchronize_session=False)
    raw_token = f"kai_enroll_{secrets.token_urlsafe(36)}"
    expires_at = now + timedelta(minutes=expires_in_minutes)
    db.add(AgentEnrollmentToken(
        server_id=server.id,
        supplier_id=user.id,
        token_hash=digest(f"agent-enrollment:{raw_token}"),
        expires_at=expires_at,
    ))
    server.agent_mode = "mtls"
    server.status = "registered"
    server.agent_revoked_at = None
    server.hardware_inventory = {}
    server.hardware_inventory_hash = None
    server.hardware_observed_at = None
    server.hardware_verified_at = None
    server.hardware_verification_status = "pending"
    server.hardware_mismatches = []
    server.agent_service_checks = {}
    server.agent_service_observed_at = None
    server.agent_service_status = "pending"
    product = db.get(Product, server.product_id)
    if product is not None:
        _pause_published_product(db, server, product, "pending")
    server.version += 1
    db.commit()
    linux_script = f"{base_url}/api/v1/agent/install/linux"
    windows_script = f"{base_url}/api/v1/agent/install/windows"
    return {
        "server_id": server.id,
        "server_no": server.server_no,
        "enrollment_token": raw_token,
        "expires_at": expires_at,
        "api_base_url": base_url,
        "linux_install_command": (
            f"curl -fsSL '{linux_script}' | sudo bash -s -- "
            f"--api-url '{base_url}' --token '{raw_token}'"
        ),
        "windows_install_command": (
            f"$script = Invoke-RestMethod '{windows_script}'; "
            f"& ([scriptblock]::Create($script)) -ApiUrl '{base_url}' -Token '{raw_token}'"
        ),
        "docker_install_command": (
            f"KAI_API_URL='{_docker_api_url(base_url)}' KAI_ENROLLMENT_TOKEN='{raw_token}' "
            "KAI_SSH_PORT=2222 docker compose up -d --build"
        ),
        "downloads": downloads(base_url),
        "security": {
            "token_single_use": True,
            "device_identity": "Ed25519 signed requests",
            "transport": "TLS required outside local development",
            "mtls_proxy_supported": True,
        },
    }


def _decode_public_key(value: str) -> bytes:
    try:
        raw = base64.b64decode(value, validate=True)
    except (binascii.Error, ValueError) as exc:
        raise ApiError("AGENT_PUBLIC_KEY_INVALID", "Agent 设备公钥编码无效", 422) from exc
    if len(raw) != 32:
        raise ApiError("AGENT_PUBLIC_KEY_INVALID", "Agent 必须使用 Ed25519 设备公钥", 422)
    return raw


def enroll_agent(
    db: Session,
    data: AgentEnrollIn,
    *,
    client_cert_fingerprint: str | None = None,
    mtls_proxy_secret: str | None = None,
) -> dict:
    now = _now()
    token = db.query(AgentEnrollmentToken).filter(
        AgentEnrollmentToken.token_hash == digest(f"agent-enrollment:{data.enrollment_token}")
    ).with_for_update().first()
    if token is None or token.used_at is not None or token.revoked_at is not None:
        raise ApiError("AGENT_ENROLLMENT_TOKEN_INVALID", "Agent 绑定码无效或已经使用", 401)
    if _aware(token.expires_at) <= now:
        raise ApiError("AGENT_ENROLLMENT_TOKEN_EXPIRED", "Agent 绑定码已经过期", 401)
    server = db.query(MerchantServer).filter(MerchantServer.id == token.server_id).with_for_update().first()
    if server is None or server.agent_revoked_at is not None:
        raise ApiError("AGENT_SERVER_UNAVAILABLE", "服务器登记不可用", 409)
    if settings.AGENT_REQUIRE_MTLS and (
        not client_cert_fingerprint
        or not mtls_proxy_secret
        or not secrets.compare_digest(mtls_proxy_secret, settings.AGENT_MTLS_PROXY_SECRET)
    ):
        raise ApiError("AGENT_MTLS_REQUIRED", "Agent 客户端证书或可信代理校验失败", 401)
    public_key = _decode_public_key(data.device_public_key)
    agent_id = uuid4().hex
    capabilities = sorted(set(data.capabilities) & SUPPORTED_CAPABILITIES)
    server.agent_device_id = agent_id
    server.agent_public_key = base64.b64encode(public_key).decode("ascii")
    server.agent_certificate_fingerprint = client_cert_fingerprint
    server.agent_platform = data.platform
    server.agent_arch = data.arch
    server.agent_hostname = data.hostname
    server.agent_version = data.version
    server.agent_capabilities = capabilities
    server.agent_enrolled_at = now
    server.agent_revoked_at = None
    server.last_seen_at = now
    server.status = "online"
    server.agent_mode = "mtls"
    product = db.get(Product, server.product_id)
    if product is None:
        raise ApiError("AGENT_PRODUCT_MISSING", "Agent 关联服务器商品不存在", 409)
    apply_hardware_inventory(db, server, product, data.inventory, observed_at=now)
    apply_service_checks(db, server, product, data.service_checks, observed_at=now)
    server.version += 1
    token.used_at = now
    db.commit()
    return {
        "agent_id": agent_id,
        "server_id": server.id,
        "server_no": server.server_no,
        "heartbeat_interval_seconds": 30,
        "poll_interval_seconds": 5,
        "signature_algorithm": "Ed25519",
        "signature_max_skew_seconds": settings.AGENT_SIGNATURE_MAX_SKEW_SECONDS,
    }


def authenticate_agent(
    db: Session,
    *,
    agent_id: str,
    timestamp: str,
    nonce: str,
    signature: str,
    method: str,
    path: str,
    body: bytes,
    client_cert_fingerprint: str | None,
    mtls_proxy_secret: str | None,
) -> MerchantServer:
    if not agent_id or not timestamp or not nonce or not signature:
        raise ApiError("AGENT_AUTH_REQUIRED", "缺少 Agent 设备签名", 401)
    if len(nonce) < 16 or len(nonce) > 64:
        raise ApiError("AGENT_NONCE_INVALID", "Agent 请求随机数无效", 401)
    try:
        sent_at = datetime.fromtimestamp(int(timestamp), tz=timezone.utc)
    except (ValueError, OverflowError) as exc:
        raise ApiError("AGENT_TIMESTAMP_INVALID", "Agent 请求时间无效", 401) from exc
    now = _now()
    if abs((now - sent_at).total_seconds()) > settings.AGENT_SIGNATURE_MAX_SKEW_SECONDS:
        raise ApiError("AGENT_CLOCK_SKEW", "Agent 系统时间偏差过大", 401)
    server = db.query(MerchantServer).filter(
        MerchantServer.agent_device_id == agent_id,
        MerchantServer.agent_revoked_at.is_(None),
    ).first()
    if server is None or not server.agent_public_key:
        raise ApiError("AGENT_IDENTITY_INVALID", "Agent 设备身份无效", 401)
    if settings.AGENT_REQUIRE_MTLS:
        proxy_trusted = bool(mtls_proxy_secret) and secrets.compare_digest(
            mtls_proxy_secret or "", settings.AGENT_MTLS_PROXY_SECRET
        )
        certificate_matches = bool(client_cert_fingerprint) and secrets.compare_digest(
            client_cert_fingerprint or "", server.agent_certificate_fingerprint or ""
        )
        if not proxy_trusted or not certificate_matches:
            raise ApiError("AGENT_MTLS_REQUIRED", "Agent 客户端证书或可信代理校验失败", 401)
    canonical = "\n".join((
        method.upper(),
        path,
        timestamp,
        nonce,
        hashlib.sha256(body).hexdigest(),
    )).encode("utf-8")
    try:
        signature_bytes = base64.b64decode(signature, validate=True)
        public_key_bytes = base64.b64decode(server.agent_public_key, validate=True)
        Ed25519PublicKey.from_public_bytes(public_key_bytes).verify(signature_bytes, canonical)
    except (ValueError, binascii.Error, InvalidSignature) as exc:
        raise ApiError("AGENT_SIGNATURE_INVALID", "Agent 设备签名无效", 401) from exc
    db.query(AgentRequestNonce).filter(AgentRequestNonce.expires_at <= now).delete(
        synchronize_session=False
    )
    db.add(AgentRequestNonce(
        nonce=nonce,
        server_id=server.id,
        expires_at=now + timedelta(seconds=settings.AGENT_SIGNATURE_MAX_SKEW_SECONDS),
    ))
    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise ApiError("AGENT_REPLAY_REJECTED", "Agent 请求已经处理", 409) from exc
    return server


def heartbeat(db: Session, server: MerchantServer, data: AgentHeartbeatIn) -> dict:
    now = _now()
    server = db.query(MerchantServer).filter(MerchantServer.id == server.id).with_for_update().one()
    server.agent_version = data.version
    server.agent_platform = data.platform
    server.agent_arch = data.arch
    server.agent_hostname = data.hostname
    server.agent_capabilities = sorted(set(data.capabilities) & SUPPORTED_CAPABILITIES)
    server.last_seen_at = now
    server.status = "online"
    product = db.get(Product, server.product_id)
    if product is None:
        raise ApiError("AGENT_PRODUCT_MISSING", "Agent 关联服务器商品不存在", 409)
    verification = apply_hardware_inventory(db, server, product, data.inventory, observed_at=now)
    service_verification = apply_service_checks(
        db, server, product, data.service_checks, observed_at=now
    )
    server.version += 1
    db.commit()
    return {
        "server_no": server.server_no,
        "status": server.status,
        "server_time": now,
        "next_heartbeat_seconds": 30,
        "hardware_verification_status": verification,
        "service_status": service_verification,
    }


def claim_command(db: Session, server: MerchantServer) -> dict | None:
    now = _now()
    db.query(AgentCommand).filter(
        AgentCommand.server_id == server.id,
        AgentCommand.status == "running",
        AgentCommand.started_at < now - timedelta(minutes=2),
    ).update({AgentCommand.status: "queued"}, synchronize_session=False)
    command = db.query(AgentCommand).filter(
        AgentCommand.server_id == server.id,
        AgentCommand.status == "queued",
    ).order_by(AgentCommand.created_at.asc(), AgentCommand.id.asc()).with_for_update().first()
    if command is None:
        db.commit()
        return None
    lease = db.get(AccessLease, command.lease_id)
    order = db.get(Order, lease.order_id) if lease else None
    command.status = "running"
    command.started_at = now
    command.attempts += 1
    db.commit()
    return {
        "command_no": command.command_no,
        "action": command.action,
        "payload": command.payload,
        "lease_no": lease.lease_no if lease else None,
        "duration_hours": order.duration_hours if order else None,
        "expires_at": lease.expires_at if lease else None,
        "grace_expires_at": lease.grace_expires_at if lease else None,
        "created_at": command.created_at,
    }


def complete_command(
    db: Session,
    server: MerchantServer,
    command_no: str,
    *,
    success: bool,
    message: str,
) -> AgentCommand:
    command = db.query(AgentCommand).filter(
        AgentCommand.command_no == command_no,
        AgentCommand.server_id == server.id,
    ).with_for_update().first()
    if command is None:
        raise ApiError("AGENT_COMMAND_NOT_FOUND", "Agent 任务不存在", 404)
    if command.status in ("succeeded", "failed"):
        return command
    if command.status != "running":
        raise ApiError("AGENT_COMMAND_STATE_INVALID", "Agent 任务当前不能回报结果", 409)
    now = _now()
    command.status = "succeeded" if success else "failed"
    command.result_message = message or ("执行成功" if success else "执行失败")
    command.completed_at = now
    lease = db.get(AccessLease, command.lease_id)
    order = db.get(Order, lease.order_id) if lease else None
    if lease is not None:
        if success and command.action == "authorize_key":
            lease.status = "active"
            lease.starts_at = lease.starts_at or now
            lease.authorized_at = now
            if lease.expires_at is None:
                duration = order.duration_hours if order and order.duration_hours else 1
                lease.expires_at = now + timedelta(hours=duration)
            lease.grace_expires_at = _aware(lease.expires_at) + timedelta(hours=2)
            lease.access_revoked_at = None
            lease.failure_reason = None
            lease.version += 1
            if order is not None and order.payment_status == "paid" and order.status == "delivering":
                order.status = "delivered"
                order.delivered_at = now
                order.delivery_note = "支付确认后，买家 SSH 公钥已通过服务器 Agent 下发"
                order.version += 1
        elif success and command.action == "revoke_key":
            lease.access_revoked_at = now
            lease.failure_reason = None
            lease.version += 1
        elif success and command.action == "cleanup_account":
            lease.cleanup_completed_at = now
            lease.failure_reason = None
            lease.version += 1
        elif not success:
            lease.failure_reason = command.result_message
            if command.action == "authorize_key" and lease.status == "pending_authorization":
                lease.status = "failed"
            lease.version += 1
        if command.action == "authorize_key":
            from app.services.server_rentals import (
                _intent_for_lease,
                release_frozen_payment,
                request_compensation_refund,
            )

            intent = _intent_for_lease(db, lease)
            if intent is not None and success:
                release_frozen_payment(db, intent)
            elif intent is not None and not success:
                request_compensation_refund(
                    db,
                    intent,
                    lease,
                    reason_code="SSH_AUTHORIZATION_FAILED",
                    reason=command.result_message or "服务器 Agent 未能完成 SSH 公钥授权",
                )
    db.commit()
    db.refresh(command)
    return command


def command_result_out(command: AgentCommand) -> dict:
    return {
        "command_no": command.command_no,
        "status": command.status,
        "result_message": command.result_message,
        "completed_at": command.completed_at,
    }


def refresh_presence(server: MerchantServer) -> None:
    last_seen = _aware(server.last_seen_at)
    if (
        server.status == "online"
        and server.agent_mode != "local_simulator"
        and (last_seen is None or last_seen < _now() - timedelta(seconds=settings.AGENT_HEARTBEAT_OFFLINE_SECONDS))
    ):
        server.status = "offline"
    if hardware_status(server) == "stale":
        server.hardware_verification_status = "stale"
    if service_status(server) == "stale":
        server.agent_service_status = "stale"


def download_path(platform: str, arch: str) -> Path:
    if platform == "docker" and arch == "context":
        path = DIST_ROOT / "kai-agent-docker-context.tar.gz"
        if not path.is_file():
            raise ApiError("AGENT_BUILD_UNAVAILABLE", "Docker Agent 源包尚未构建", 503)
        return path
    for candidate_platform, candidate_arch, filename in DOWNLOAD_TARGETS:
        if platform == candidate_platform and arch == candidate_arch:
            path = DIST_ROOT / filename
            if not path.is_file():
                raise ApiError("AGENT_BUILD_UNAVAILABLE", "Agent 安装包尚未构建", 503)
            return path
    raise ApiError("AGENT_DOWNLOAD_NOT_FOUND", "不支持这个系统或架构", 404)
